"""align rifa_numeros schema

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-04
"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rifa_numeros", sa.Column("orden_aleatorio", sa.Integer(), nullable=True))

    op.execute(
        """
        WITH ranked AS (
            SELECT
                rifa_id,
                numero,
                ROW_NUMBER() OVER (PARTITION BY rifa_id ORDER BY random()) AS orden
            FROM rifa_numeros
        )
        UPDATE rifa_numeros rn
        SET orden_aleatorio = ranked.orden
        FROM ranked
        WHERE rn.rifa_id = ranked.rifa_id
          AND rn.numero = ranked.numero
        """
    )

    op.alter_column("rifa_numeros", "orden_aleatorio", nullable=False)

    op.create_index(
        "ix_rifa_numeros_rifa_id_asignado_orden",
        "rifa_numeros",
        ["rifa_id", "asignado", "orden_aleatorio"],
    )

    op.drop_column("rifa_numeros", "cliente_id")
    op.drop_column("rifa_numeros", "suscripcion_id")
    op.drop_column("rifa_numeros", "asignado_en")


def downgrade() -> None:
    op.add_column(
        "rifa_numeros",
        sa.Column("asignado_en", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "rifa_numeros",
        sa.Column("suscripcion_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "rifa_numeros",
        sa.Column("cliente_id", sa.UUID(), nullable=True),
    )

    op.drop_index("ix_rifa_numeros_rifa_id_asignado_orden", table_name="rifa_numeros")
    op.drop_column("rifa_numeros", "orden_aleatorio")
