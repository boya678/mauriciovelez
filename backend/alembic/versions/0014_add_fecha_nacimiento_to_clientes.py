"""add fecha_nacimiento to clientes

Revision ID: 0014
Revises: 0013
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clientes",
        sa.Column("fecha_nacimiento", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clientes", "fecha_nacimiento")
