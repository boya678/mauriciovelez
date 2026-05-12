"""Add public.knowledge_chunks table for RAG.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-11 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
        CREATE TABLE IF NOT EXISTS public.knowledge_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding vector(1536),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # IVFFlat index for fast approximate cosine search (max 2000 dims supported)
    op.execute("""
        CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
        ON public.knowledge_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS knowledge_chunks_tenant_idx
        ON public.knowledge_chunks (tenant_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.knowledge_chunks")
