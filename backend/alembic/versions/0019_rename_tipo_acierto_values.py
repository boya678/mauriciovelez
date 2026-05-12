"""rename tipo values in numero_aciertos

exacto           -> directo
directo_devuelto -> directo_metodo
tres_orden       -> tres_directo
tres_desorden    -> tres_metodo

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-11
"""
from alembic import op

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE numero_aciertos SET tipo = 'directo'        WHERE tipo = 'exacto'")
    op.execute("UPDATE numero_aciertos SET tipo = 'directo_metodo' WHERE tipo = 'directo_devuelto'")
    op.execute("UPDATE numero_aciertos SET tipo = 'tres_directo'   WHERE tipo = 'tres_orden'")
    op.execute("UPDATE numero_aciertos SET tipo = 'tres_metodo'    WHERE tipo = 'tres_desorden'")


def downgrade() -> None:
    op.execute("UPDATE numero_aciertos SET tipo = 'exacto'           WHERE tipo = 'directo'")
    op.execute("UPDATE numero_aciertos SET tipo = 'directo_devuelto' WHERE tipo = 'directo_metodo'")
    op.execute("UPDATE numero_aciertos SET tipo = 'tres_orden'       WHERE tipo = 'tres_directo'")
    op.execute("UPDATE numero_aciertos SET tipo = 'tres_desorden'    WHERE tipo = 'tres_metodo'")
