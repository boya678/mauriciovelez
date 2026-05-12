"""
RAG knowledge service.

Responsibilities:
  - chunk_text     : split a plain-text document into overlapping chunks
  - embed_texts    : call Azure OpenAI Embeddings in batch, return list of vectors
  - upsert_knowledge : delete existing chunks for a tenant and insert new ones
  - search_knowledge : cosine-similarity search, returns top-k chunk contents
  - knowledge_status : count of chunks stored for a tenant
"""
from __future__ import annotations

import logging
import uuid
from typing import List

from openai import AsyncAzureOpenAI
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── OpenAI async client (re-used across calls) ────────────────────────────────

_openai_client: AsyncAzureOpenAI | None = None


def _get_openai() -> AsyncAzureOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncAzureOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION_EMBEDDING,
        )
    return _openai_client


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_text(
    text_content: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> List[str]:
    """
    Split text into word-based chunks of `chunk_size` words with `overlap` words
    of overlap between consecutive chunks.
    Returns a list of non-empty strings.
    """
    words = text_content.split()
    if not words:
        return []

    chunks: List[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end == len(words):
            break
        start += chunk_size - overlap

    return chunks


# ── Embedding ─────────────────────────────────────────────────────────────────

async def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Embed a batch of texts with text-embedding-3-large reduced to 1536 dimensions.
    1536 dims stays within the pgvector index limit (2000) while retaining
    excellent retrieval quality.
    Returns a list of float vectors in the same order as the input.
    """
    client = _get_openai()
    response = await client.embeddings.create(
        model=settings.AZURE_OPENAI_EMBEDDING_MODEL,
        input=texts,
        dimensions=1536,
    )
    # API returns items sorted by index
    items = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in items]


# ── Upsert ────────────────────────────────────────────────────────────────────

async def upsert_knowledge(
    tenant_id: uuid.UUID,
    text_content: str,
    db: AsyncSession,
) -> int:
    """
    Replace all knowledge chunks for a tenant with chunks derived from
    `text_content`. Returns the number of chunks stored.
    """
    # Delete existing chunks for this tenant
    await db.execute(
        text("DELETE FROM public.knowledge_chunks WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    )

    chunks = chunk_text(text_content)
    if not chunks:
        await db.commit()
        return 0

    # Embed all chunks in one batch call
    vectors = await embed_texts(chunks)

    # Bulk insert using raw SQL with pgvector cast
    for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
        vector_str = "[" + ",".join(str(v) for v in vector) + "]"
        await db.execute(
            text(
                "INSERT INTO public.knowledge_chunks "
                "(id, tenant_id, chunk_index, content, embedding, created_at) "
                "VALUES (gen_random_uuid(), :tid, :idx, :content, :vec::vector, NOW())"
            ),
            {"tid": tenant_id, "idx": idx, "content": chunk, "vec": vector_str},
        )

    await db.commit()
    logger.info("Upserted %d knowledge chunks for tenant %s", len(chunks), tenant_id)
    return len(chunks)


# ── Search ────────────────────────────────────────────────────────────────────

async def search_knowledge(
    tenant_id: uuid.UUID,
    query: str,
    db: AsyncSession,
    top_k: int = 3,
) -> List[str]:
    """
    Embed `query` and return the top_k most similar chunk contents for the tenant.
    Returns an empty list if the tenant has no knowledge loaded.
    """
    # Fast check: does this tenant have any chunks?
    count_row = await db.execute(
        text(
            "SELECT COUNT(*) FROM public.knowledge_chunks WHERE tenant_id = :tid"
        ),
        {"tid": tenant_id},
    )
    count = count_row.scalar()
    if not count:
        return []

    # Embed the query (single text)
    vectors = await embed_texts([query])
    query_vector = vectors[0]
    vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

    rows = await db.execute(
        text(
            "SELECT content "
            "FROM public.knowledge_chunks "
            "WHERE tenant_id = :tid "
            "ORDER BY embedding <=> :vec::vector "
            "LIMIT :k"
        ),
        {"tid": tenant_id, "vec": vector_str, "k": top_k},
    )
    return [row[0] for row in rows.fetchall()]


# ── Status ────────────────────────────────────────────────────────────────────

async def knowledge_status(
    tenant_id: uuid.UUID,
    db: AsyncSession,
) -> int:
    """Return the number of chunks stored for a tenant."""
    row = await db.execute(
        text(
            "SELECT COUNT(*) FROM public.knowledge_chunks WHERE tenant_id = :tid"
        ),
        {"tid": tenant_id},
    )
    return row.scalar() or 0
