"""Fix knowledge_chunks: drop table with wrong vector dims and recreate with vector(1536).

The previous migration (0008) partially applied: the table was created with
vector(3072) but the index failed (pgvector index limit is 2000 dimensions).
This migration drops and recreates the table correctly with vector(1536) and
an ivfflat index.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-11 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the partially-created table (wrong column type + missing index)
    op.execute("DROP TABLE IF EXISTS public.knowledge_chunks")

    # Recreate with vector(1536) — within the pgvector 2000-dim index limit
    # text-embedding-3-large supports dimension reduction via the API `dimensions` param
    op.execute("""
        CREATE TABLE public.knowledge_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding vector(1536),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX knowledge_chunks_embedding_idx
        ON public.knowledge_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    op.execute("""
        CREATE INDEX knowledge_chunks_tenant_idx
        ON public.knowledge_chunks (tenant_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.knowledge_chunks")
