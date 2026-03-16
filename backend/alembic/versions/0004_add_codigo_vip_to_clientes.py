"""add codigo_vip to clientes

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clientes",
        sa.Column("codigo_vip", sa.String(50), nullable=True),
    )
    op.create_unique_constraint("uq_clientes_codigo_vip", "clientes", ["codigo_vip"])


def downgrade() -> None:
    op.drop_constraint("uq_clientes_codigo_vip", "clientes", type_="unique")
    op.drop_column("clientes", "codigo_vip")
