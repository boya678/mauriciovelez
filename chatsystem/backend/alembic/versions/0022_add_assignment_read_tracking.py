"""Add per-agent conversation read tracking.

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-07
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
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
            f"ALTER TABLE {schema}.assignments "
            "ADD COLUMN IF NOT EXISTS last_read_at TIMESTAMPTZ"
        )
        op.execute(
            f"UPDATE {schema}.assignments "
            "SET last_read_at = now() "
            "WHERE released_at IS NULL AND last_read_at IS NULL"
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_assign_active_read "
            f"ON {schema}.assignments (conversation_id, agent_id) "
            "WHERE released_at IS NULL"
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
        op.execute(f"DROP INDEX IF EXISTS {schema}.ix_assign_active_read")
        op.execute(
            f"ALTER TABLE {schema}.assignments "
            "DROP COLUMN IF EXISTS last_read_at"
        )