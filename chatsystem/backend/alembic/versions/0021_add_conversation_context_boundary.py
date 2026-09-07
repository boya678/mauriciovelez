"""Add a durable AI context boundary to tenant conversations.

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-07
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

TENANT_SCHEMA_PATTERN = re.compile(r"^t_[a-z0-9_]+$")


def _safe_schema(schema: str) -> str:
    if not TENANT_SCHEMA_PATTERN.fullmatch(schema):
        raise ValueError(f"Unexpected tenant schema name: {schema!r}")
    return schema


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("SET LOCAL lock_timeout = '60s'"))
    schemas = conn.execute(
        sa.text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 't_%'"
        )
    ).fetchall()

    for (schema_name,) in schemas:
        schema = _safe_schema(schema_name)
        op.execute(
            f"ALTER TABLE {schema}.conversations "
            "ADD COLUMN IF NOT EXISTS context_started_at TIMESTAMPTZ"
        )
        op.execute(
            f"UPDATE {schema}.conversations "
            "SET context_started_at = COALESCE(closed_at, created_at) "
            "WHERE context_started_at IS NULL"
        )


def downgrade() -> None:
    conn = op.get_bind()
    schemas = conn.execute(
        sa.text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 't_%'"
        )
    ).fetchall()

    for (schema_name,) in schemas:
        schema = _safe_schema(schema_name)
        op.execute(
            f"ALTER TABLE {schema}.conversations "
            "DROP COLUMN IF EXISTS context_started_at"
        )