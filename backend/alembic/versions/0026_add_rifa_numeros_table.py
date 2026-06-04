"""add rifa_numeros table

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rifa_numeros",
        sa.Column(
            "rifa_id",
            UUID(as_uuid=True),
            sa.ForeignKey("rifas.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("numero", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("orden_aleatorio", sa.Integer(), nullable=False),
        sa.Column("asignado", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_index("ix_rifa_numeros_rifa_id", "rifa_numeros", ["rifa_id"])
    op.create_index(
        "ix_rifa_numeros_rifa_id_asignado_orden",
        "rifa_numeros",
        ["rifa_id", "asignado", "orden_aleatorio"],
    )


def downgrade() -> None:
    op.drop_index("ix_rifa_numeros_rifa_id_asignado_orden", table_name="rifa_numeros")
    op.drop_index("ix_rifa_numeros_rifa_id", table_name="rifa_numeros")
    op.drop_table("rifa_numeros")
