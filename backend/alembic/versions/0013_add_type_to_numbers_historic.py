"""add_type_to_numbers_historic

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "numbers_historic",
        sa.Column("type", sa.String(10), nullable=True),
    )
    # Registros existentes se marcan como 'free' por defecto
    op.execute("UPDATE numbers_historic SET type = 'free' WHERE type IS NULL")
    op.alter_column("numbers_historic", "type", nullable=False)


def downgrade() -> None:
    op.drop_column("numbers_historic", "type")
