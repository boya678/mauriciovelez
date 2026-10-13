"""Add indexes needed to keep the inbox list fast as tenants grow.

Without ix_conv_tenant_context_started, listing the oldest-first inbox page
forces Postgres to compute the per-conversation "latest message"/"unread
count" subqueries for every conversation in the tenant before sorting and
limiting to the visible page. ix_msg_conv_created speeds up those same
subqueries regardless of how many conversations are scanned.

Uses CREATE INDEX CONCURRENTLY (via autocommit_block) so building the index
on a large, live messages table doesn't block reads/writes.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-13
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

TENANT_SCHEMA_PATTERN = re.compile(r"^t_[a-z0-9_]+$")


def _safe_schema(schema: str) -> str:
    if not TENANT_SCHEMA_PATTERN.fullmatch(schema):
        raise ValueError(f"Unexpected tenant schema name: {schema!r}")
    return schema


def upgrade() -> None:
    conn = op.get_bind()
    schemas = conn.execute(
        sa.text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 't_%'"
        )
    ).fetchall()

    for (schema_name,) in schemas:
        schema = _safe_schema(schema_name)
        with op.get_context().autocommit_block():
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_conv_tenant_context_started "
                f"ON {schema}.conversations (tenant_id, context_started_at)"
            )
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_msg_conv_created "
                f"ON {schema}.messages (conversation_id, created_at DESC)"
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
        with op.get_context().autocommit_block():
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {schema}.ix_conv_tenant_context_started")
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {schema}.ix_msg_conv_created")
