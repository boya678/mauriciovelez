"""add message_stats table

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-11
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.message_stats (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            year            SMALLINT NOT NULL,
            month           SMALLINT NOT NULL,
            bot_messages    BIGINT NOT NULL DEFAULT 0,
            human_messages  BIGINT NOT NULL DEFAULT 0,
            user_messages   BIGINT NOT NULL DEFAULT 0,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, year, month)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_message_stats_tenant_period
            ON public.message_stats (tenant_id, year, month)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.message_stats")
