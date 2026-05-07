"""Add public.agent_tools table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE tool_type AS ENUM ('HTTP', 'SQL', 'STATIC');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS public.agent_tools (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            name        VARCHAR(100) NOT NULL,
            description TEXT NOT NULL,
            tool_type   tool_type NOT NULL,
            enabled     BOOLEAN NOT NULL DEFAULT true,
            http_url            TEXT,
            http_method         VARCHAR(10) DEFAULT 'GET',
            http_headers        JSONB,
            http_body_tpl       TEXT,
            http_timeout_seconds INTEGER DEFAULT 10,
            sql_dsn     TEXT,
            sql_query   TEXT,
            sql_params  JSONB,
            static_text TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_agent_tools_tenant_enabled
        ON public.agent_tools (tenant_id, enabled)
    """)


def downgrade() -> None:
    op.drop_index("ix_agent_tools_tenant_enabled", table_name="agent_tools", schema="public")
    op.drop_table("agent_tools", schema="public")
    op.execute("DROP TYPE IF EXISTS tool_type")
