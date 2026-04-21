"""add parametros table

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parametros",
        sa.Column("clave", sa.String(50), primary_key=True),
        sa.Column("valor", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.String(500), nullable=True),
    )
    op.execute("""
        INSERT INTO parametros (clave, valor, descripcion) VALUES
        ('vigencia_free', '10', 'Duración en días de cada ciclo de número free'),
        ('vigencia_vip', '3', 'Duración en días de cada ciclo de número VIP'),
        ('epoch_numeros', '2026-01-01', 'Fecha de inicio de los ciclos de números (formato YYYY-MM-DD)')
    """)


def downgrade() -> None:
    op.drop_table("parametros")
