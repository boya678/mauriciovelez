"""Add public.agent_tools table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-02 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE tool_type AS ENUM ('HTTP', 'SQL', 'STATIC')")

    op.create_table(
        "agent_tools",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column(
            "tool_type",
            sa.Enum("HTTP", "SQL", "STATIC", name="tool_type", create_type=False),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        # HTTP fields
        sa.Column("http_url", sa.Text, nullable=True),
        sa.Column("http_method", sa.String(10), nullable=True, server_default="GET"),
        sa.Column("http_headers", postgresql.JSONB, nullable=True),
        sa.Column("http_body_tpl", sa.Text, nullable=True),
        sa.Column("http_timeout_seconds", sa.Integer, nullable=True, server_default="10"),
        # SQL fields
        sa.Column("sql_dsn", sa.Text, nullable=True),
        sa.Column("sql_query", sa.Text, nullable=True),
        sa.Column("sql_params", postgresql.JSONB, nullable=True),
        # STATIC fields
        sa.Column("static_text", sa.Text, nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="public",
    )

    op.create_index(
        "ix_agent_tools_tenant_enabled",
        "agent_tools",
        ["tenant_id", "enabled"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index("ix_agent_tools_tenant_enabled", table_name="agent_tools", schema="public")
    op.drop_table("agent_tools", schema="public")
    op.execute("DROP TYPE IF EXISTS tool_type")
