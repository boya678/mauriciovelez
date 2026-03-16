"""add cuentas_vip table

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cuentas_vip",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("anio", sa.Integer(), nullable=False),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("anio", "mes", name="uq_cuenta_vip_anio_mes"),
    )


def downgrade() -> None:
    op.drop_table("cuentas_vip")
