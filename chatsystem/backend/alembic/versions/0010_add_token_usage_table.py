"""add token_usage table

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.token_usage (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            year        SMALLINT NOT NULL,
            month       SMALLINT NOT NULL,
            tokens_in   BIGINT NOT NULL DEFAULT 0,
            tokens_out  BIGINT NOT NULL DEFAULT 0,
            tokens_total BIGINT NOT NULL DEFAULT 0,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, year, month)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_token_usage_tenant_period
            ON public.token_usage (tenant_id, year, month)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.token_usage")
