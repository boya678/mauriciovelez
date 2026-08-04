"""Add bsuid column to conversations in all tenant schemas.

bsuid stores the Business-Scoped User ID (e.g. "CO.1949266959121697") as
a stable, permanent identifier separate from the phone number field.
Once a user shares their real phone via pedir_contacto, conversations.phone
is updated to the real number while bsuid stays untouched.

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
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
            f"ADD COLUMN IF NOT EXISTS bsuid VARCHAR(150) NULL"
        )
        # Index for BSUID lookups on incoming messages
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_conv_bsuid "
            f"ON {schema}.conversations (bsuid)"
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
            f"DROP INDEX IF EXISTS {schema}.ix_conv_bsuid"
        )
        op.execute(
            f"ALTER TABLE {schema}.conversations "
            f"DROP COLUMN IF EXISTS bsuid"
        )
