"""add suscripciones table

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suscripciones",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cliente_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clientes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fin", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_suscripciones_cliente_id", "suscripciones", ["cliente_id"])
    op.create_index("ix_suscripciones_fin", "suscripciones", ["fin"])


def downgrade() -> None:
    op.drop_index("ix_suscripciones_fin", "suscripciones")
    op.drop_index("ix_suscripciones_cliente_id", "suscripciones")
    op.drop_table("suscripciones")
