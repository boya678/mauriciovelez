"""add_referente_to_clientes

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-11
"""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clientes", sa.Column("referente", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("clientes", "referente")
