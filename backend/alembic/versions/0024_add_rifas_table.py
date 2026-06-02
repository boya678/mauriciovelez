"""add rifas table

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rifas",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("imagen_data", sa.LargeBinary(), nullable=True),
        sa.Column("imagen_mime", sa.String(50), nullable=True),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date(), nullable=False),
        sa.Column("seq_inicio", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seq_fin", sa.Integer(), nullable=False, server_default="9999"),
        sa.Column("boletas_por_renovacion", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("solo_vip", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("tipos_cliente", JSONB(), nullable=False, server_default="[]"),
        sa.Column("ganador_numero", sa.Integer(), nullable=True),
        sa.Column("estado", sa.String(20), nullable=False, server_default="activa"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "rifa_boletas",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rifa_id",
            UUID(as_uuid=True),
            sa.ForeignKey("rifas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cliente_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clientes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "suscripcion_id",
            UUID(as_uuid=True),
            sa.ForeignKey("suscripciones.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column(
            "asignado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_rifa_boletas_rifa_id", "rifa_boletas", ["rifa_id"])
    op.create_index("ix_rifa_boletas_cliente_id", "rifa_boletas", ["cliente_id"])
    op.create_unique_constraint(
        "uq_rifa_boleta_numero", "rifa_boletas", ["rifa_id", "numero"]
    )


def downgrade() -> None:
    op.drop_table("rifa_boletas")
    op.drop_table("rifas")
