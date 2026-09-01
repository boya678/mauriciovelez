"""add destino validation fields to mensajes_ia_procesados

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-31
"""
from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mensajes_ia_procesados",
        sa.Column("numero_destino", sa.String(50), nullable=True),
    )
    op.add_column(
        "mensajes_ia_procesados",
        sa.Column("nombre_destino", sa.String(200), nullable=True),
    )
    op.add_column(
        "mensajes_ia_procesados",
        sa.Column("destino_valido", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("mensajes_ia_procesados", "destino_valido")
    op.drop_column("mensajes_ia_procesados", "nombre_destino")
    op.drop_column("mensajes_ia_procesados", "numero_destino")
