"""add mensajes_ia_procesados and comprobantes_vip tables

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mensajes_ia_procesados",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("message_id", UUID(as_uuid=True), nullable=False),
        sa.Column("es_comprobante", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("monto_extraido", sa.Numeric(18, 2), nullable=True),
        sa.Column("comprobante_num", sa.String(200), nullable=True),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_mensajes_ia_procesados_message_id", "mensajes_ia_procesados", ["message_id"], unique=True)

    op.create_table(
        "comprobantes_vip",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("comprobante_num", sa.String(200), nullable=False),
        sa.Column("celular", sa.String(30), nullable=False),
        sa.Column("monto", sa.Numeric(18, 2), nullable=False),
        sa.Column("message_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_comprobantes_vip_comprobante_num", "comprobantes_vip", ["comprobante_num"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_comprobantes_vip_comprobante_num", table_name="comprobantes_vip")
    op.drop_table("comprobantes_vip")
    op.drop_index("ix_mensajes_ia_procesados_message_id", table_name="mensajes_ia_procesados")
    op.drop_table("mensajes_ia_procesados")
