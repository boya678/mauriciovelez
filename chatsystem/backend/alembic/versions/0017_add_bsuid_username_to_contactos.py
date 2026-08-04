"""Add bsuid and username columns to contactos in all tenant schemas.

bsuid  — links a WhatsApp Business-Scoped User ID to the stored phone number.
         Unique per tenant schema so we can look up "do we already have
         a phone for this BSUID?" in a single query.
username — WhatsApp username (display name) associated with the contact.

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
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
            f"ALTER TABLE {schema}.contactos "
            f"ADD COLUMN IF NOT EXISTS bsuid VARCHAR(150) NULL"
        )
        op.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS ix_contactos_bsuid "
            f"ON {schema}.contactos (bsuid) WHERE bsuid IS NOT NULL"
        )
        op.execute(
            f"ALTER TABLE {schema}.contactos "
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
        op.execute(f"DROP INDEX IF EXISTS {schema}.ix_contactos_bsuid")
        op.execute(
            f"ALTER TABLE {schema}.contactos DROP COLUMN IF EXISTS bsuid"
        )
        op.execute(
            f"ALTER TABLE {schema}.contactos DROP COLUMN IF EXISTS username"
        )
