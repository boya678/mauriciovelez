"""add image_hash to mensajes_ia_procesados and comprobantes_vip

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # mensajes_ia_procesados: agregar image_hash (nullable, con índice)
    op.add_column(
        "mensajes_ia_procesados",
        sa.Column("image_hash", sa.String(64), nullable=True),
    )
    op.create_index("ix_mensajes_ia_image_hash", "mensajes_ia_procesados", ["image_hash"])

    # comprobantes_vip: agregar image_hash (nullable, UNIQUE)
    op.add_column(
        "comprobantes_vip",
        sa.Column("image_hash", sa.String(64), nullable=True),
    )
    op.create_index("ix_comprobantes_vip_image_hash", "comprobantes_vip", ["image_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_comprobantes_vip_image_hash", table_name="comprobantes_vip")
    op.drop_column("comprobantes_vip", "image_hash")
    op.drop_index("ix_mensajes_ia_image_hash", table_name="mensajes_ia_procesados")
    op.drop_column("mensajes_ia_procesados", "image_hash")
