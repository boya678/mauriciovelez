"""add numeros_rifa_entregados table and rifa counter parameter

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "numeros_rifa_entregados",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("numero", sa.String(4), nullable=False),
        sa.Column("cliente_id", UUID(as_uuid=True), nullable=True),
        sa.Column("celular", sa.String(30), nullable=False),
        sa.Column("descripcion", sa.String(200), nullable=False),
        sa.Column("message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_numeros_rifa_entregados_created_at", "numeros_rifa_entregados", ["created_at"])
    op.execute(
        "INSERT INTO parametros (clave, valor, descripcion) VALUES "
        "('servicio_relampago_personalizado_rifa_siguiente', '0', 'Proximo numero de rifa a entregar (0-9999)') "
        "ON CONFLICT (clave) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM parametros WHERE clave = 'servicio_relampago_personalizado_rifa_siguiente'")
    op.drop_index("ix_numeros_rifa_entregados_created_at", table_name="numeros_rifa_entregados")
    op.drop_table("numeros_rifa_entregados")
