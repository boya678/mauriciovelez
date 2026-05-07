"""Add media_content and media_mime_type to messages table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add to the public schema messages table (shared by all tenants via inheritance/schema)
    # Each tenant schema has its own messages table — iterate over all t_* schemas
    conn = op.get_bind()
    schemas = conn.execute(
        sa.text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 't_%'"
        )
    ).fetchall()

    for (schema,) in schemas:
        op.execute(
            f"ALTER TABLE {schema}.messages "
            f"ADD COLUMN IF NOT EXISTS media_content TEXT, "
            f"ADD COLUMN IF NOT EXISTS media_mime_type VARCHAR(100)"
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
            f"ALTER TABLE {schema}.messages "
            f"DROP COLUMN IF EXISTS media_content, "
            f"DROP COLUMN IF EXISTS media_mime_type"
        )
