"""add registro_completado to clientes

Existing clients stay as completed; clients created by services start as pending.

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clientes",
        sa.Column("registro_completado", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("clientes", "registro_completado")
