"""Add username column to conversations in all tenant schemas.

Stores the WhatsApp username (@handle) for contacts that hide their phone
number and are identified by BSUID (Business-Scoped User ID).

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
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
        op.execute(
            f"ALTER TABLE {schema}.conversations "
            f"ADD COLUMN IF NOT EXISTS username VARCHAR(100) NULL"
        )


def downgrade() -> None:
    conn = op.get_bind()
    schemas = conn.execute(
        sa.text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 't_%'"
        )
    ).fetchall()

    for (schema,) in schemas:
        op.execute(
            f"ALTER TABLE {schema}.conversations "
            f"DROP COLUMN IF EXISTS username"
        )
