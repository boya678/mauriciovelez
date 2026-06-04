"""add transacciones_procesadas table

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transacciones_procesadas",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("id_externo", UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("estado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_transacciones_procesadas_id_externo",
        "transacciones_procesadas",
        ["id_externo"],
    )


def downgrade() -> None:
    op.drop_index("ix_transacciones_procesadas_id_externo", table_name="transacciones_procesadas")
    op.drop_table("transacciones_procesadas")
