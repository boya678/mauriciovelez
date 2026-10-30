"""add rifa_enum_avisos and aviso_id on rifa_enum_boletas (boletas are delivered after the customer asks for them)

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rifa_enum_avisos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lote_id", sa.Integer(), nullable=False),
        sa.Column("celular", sa.String(20), nullable=False),
        sa.Column("celular_local", sa.String(10), nullable=False),
        sa.Column("estado", sa.String(10), nullable=False, server_default="pendiente"),
        sa.Column("wamid", sa.String(120), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("enviado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("solicitada_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["lote_id"], ["rifa_enum_lotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rifa_enum_avisos_lote_id", "rifa_enum_avisos", ["lote_id"])
    op.create_index("ix_rifa_enum_avisos_celular_local", "rifa_enum_avisos", ["celular_local"])
    op.create_index("ix_rifa_enum_avisos_wamid", "rifa_enum_avisos", ["wamid"])

    op.add_column("rifa_enum_boletas", sa.Column("aviso_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_rifa_enum_boletas_aviso_id", "rifa_enum_boletas", "rifa_enum_avisos", ["aviso_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_rifa_enum_boletas_aviso_id", "rifa_enum_boletas", ["aviso_id"])


def downgrade() -> None:
    op.drop_index("ix_rifa_enum_boletas_aviso_id", table_name="rifa_enum_boletas")
    op.drop_constraint("fk_rifa_enum_boletas_aviso_id", "rifa_enum_boletas", type_="foreignkey")
    op.drop_column("rifa_enum_boletas", "aviso_id")
    op.drop_table("rifa_enum_avisos")
