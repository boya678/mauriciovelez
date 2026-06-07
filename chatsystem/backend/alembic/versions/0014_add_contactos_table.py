"""Add contactos table to all tenant schemas and seed existing phones.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    schemas = conn.execute(
        sa.text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 't_%'"
        )
    ).fetchall()

    for (schema,) in schemas:
        # Create table
        op.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema}.contactos (
                id VARCHAR(30) PRIMARY KEY,
                tags TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        # Seed with all distinct phones that already have conversations
        op.execute(f"""
            INSERT INTO {schema}.contactos (id, tags, created_at)
            SELECT DISTINCT phone, '', NOW()
            FROM {schema}.conversations
            ON CONFLICT (id) DO NOTHING
        """)


def downgrade() -> None:
    conn = op.get_bind()
    schemas = conn.execute(
        sa.text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 't_%'"
        )
    ).fetchall()

    for (schema,) in schemas:
        op.execute(f"DROP TABLE IF EXISTS {schema}.contactos")
