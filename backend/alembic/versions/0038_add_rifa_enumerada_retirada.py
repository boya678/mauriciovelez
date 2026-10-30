"""add retirada columns to rifa_enum_boletas

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rifa_enum_boletas", sa.Column("retirada", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("rifa_enum_boletas", sa.Column("retirada_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("rifa_enum_boletas", sa.Column("retirada_por", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("rifa_enum_boletas", "retirada_por")
    op.drop_column("rifa_enum_boletas", "retirada_at")
    op.drop_column("rifa_enum_boletas", "retirada")
