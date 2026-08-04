"""add descripcion to comprobantes_vip

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "comprobantes_vip",
        sa.Column("descripcion", sa.String(300), nullable=False, server_default="pago vip"),
    )


def downgrade() -> None:
    op.drop_column("comprobantes_vip", "descripcion")
