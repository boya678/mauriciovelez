"""Add imagen_descripcion to messages table.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-06 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
            f"ALTER TABLE {schema}.messages "
            f"ADD COLUMN IF NOT EXISTS imagen_descripcion TEXT"
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
            f"DROP COLUMN IF EXISTS imagen_descripcion"
        )
