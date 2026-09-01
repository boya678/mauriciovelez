"""Add durable inactivity tracking to tenant conversations.

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-01
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

TENANT_SCHEMA_PATTERN = re.compile(r"^t_[a-z0-9_]+$")


def _safe_schema(schema: str) -> str:
    if not TENANT_SCHEMA_PATTERN.fullmatch(schema):
        raise ValueError(f"Unexpected tenant schema name: {schema!r}")
    return schema


def upgrade() -> None:
    conn = op.get_bind()
    # Do not sit silently behind an abandoned application transaction. This
    # produces a concrete lock-timeout error that identifies the real problem.
    conn.execute(sa.text("SET LOCAL lock_timeout = '60s'"))
    conn.execute(sa.text("SET LOCAL statement_timeout = '15min'"))
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
            "ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ"
        )
        op.execute(
            f"ALTER TABLE {schema}.conversations "
            "ADD COLUMN IF NOT EXISTS idle_warning_sent_at TIMESTAMPTZ"
        )
        op.execute(
            f"ALTER TABLE {schema}.conversations "
            "ADD COLUMN IF NOT EXISTS handoff_notice_sent_at TIMESTAMPTZ"
        )
        op.execute(
            f"UPDATE {schema}.conversations "
            "SET last_activity_at = NOW() "
            "WHERE last_activity_at IS NULL"
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_conv_idle_scan "
            f"ON {schema}.conversations (status, last_activity_at)"
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
        op.execute(f"DROP INDEX IF EXISTS {schema}.ix_conv_idle_scan")
        op.execute(
            f"ALTER TABLE {schema}.conversations "
            "DROP COLUMN IF EXISTS handoff_notice_sent_at"
        )
        op.execute(
            f"ALTER TABLE {schema}.conversations "
            "DROP COLUMN IF EXISTS idle_warning_sent_at"
        )
        op.execute(
            f"ALTER TABLE {schema}.conversations "
            "DROP COLUMN IF EXISTS last_activity_at"
        )