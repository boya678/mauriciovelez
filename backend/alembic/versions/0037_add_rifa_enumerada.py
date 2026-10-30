"""add rifa enumerada tables (base image, shuffled number pool, lotes, boletas)

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rifa_enum_base",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("imagen_data", sa.LargeBinary(), nullable=False),
        sa.Column("imagen_mime", sa.String(50), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rifa_enum_numeros",
        sa.Column("numero", sa.String(4), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("numero"),
    )
    op.create_index("ix_rifa_enum_numeros_orden", "rifa_enum_numeros", ["orden"])
    # Los 10.000 números en orden aleatorio; el puntero vive en parametros.
    op.execute(
        "INSERT INTO rifa_enum_numeros (numero, orden) "
        "SELECT lpad(g::text, 4, '0'), (ROW_NUMBER() OVER (ORDER BY random())) - 1 "
        "FROM generate_series(0, 9999) AS g"
    )
    op.execute(
        "INSERT INTO parametros (clave, valor, descripcion) VALUES "
        "('servicio_rifa_enum_siguiente', '0', 'Proxima posicion (0-9999) de la lista barajada de la rifa enumerada') "
        "ON CONFLICT (clave) DO NOTHING"
    )

    op.create_table(
        "rifa_enum_lotes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("usuario", sa.String(100), nullable=False),
        sa.Column("archivo", sa.String(200), nullable=False),
        sa.Column("celulares", sa.Text(), nullable=False),
        sa.Column("total_filas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("validas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalidas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicadas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalidas_json", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(12), nullable=False, server_default="cargado"),
        sa.Column("incluir_repetidos", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cantidad", sa.Integer(), nullable=True),
        sa.Column("iniciado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalizado_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rifa_enum_boletas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lote_id", sa.Integer(), nullable=False),
        sa.Column("celular", sa.String(20), nullable=False),
        sa.Column("celular_local", sa.String(10), nullable=False),
        sa.Column("numero", sa.String(4), nullable=False),
        sa.Column("ronda", sa.Integer(), nullable=False),
        sa.Column("estado_envio", sa.String(12), nullable=False, server_default="pendiente"),
        sa.Column("wamid", sa.String(120), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("enviada_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pagada", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("pagada_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comprobante_num", sa.String(200), nullable=True),
        sa.Column("pago_monto", sa.Numeric(18, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["lote_id"], ["rifa_enum_lotes.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_rifa_enum_boletas_lote_estado", "rifa_enum_boletas", ["lote_id", "estado_envio"])
    op.create_index("ix_rifa_enum_boletas_celular", "rifa_enum_boletas", ["celular"])
    op.create_index("ix_rifa_enum_boletas_local_pagada", "rifa_enum_boletas", ["celular_local", "pagada"])
    op.create_index("ix_rifa_enum_boletas_created_at", "rifa_enum_boletas", ["created_at"])


def downgrade() -> None:
    op.drop_table("rifa_enum_boletas")
    op.drop_table("rifa_enum_lotes")
    op.execute("DELETE FROM parametros WHERE clave = 'servicio_rifa_enum_siguiente'")
    op.drop_table("rifa_enum_numeros")
    op.drop_table("rifa_enum_base")
