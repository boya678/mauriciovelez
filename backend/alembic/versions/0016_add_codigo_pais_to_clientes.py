"""add codigo_pais to clientes

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'clientes',
        sa.Column('codigo_pais', sa.String(10), nullable=True, server_default='57'),
    )
    # Rellenar los existentes: si el celular empieza con un código de país conocido, extraerlo
    op.execute("""
        UPDATE clientes
        SET codigo_pais = '57'
        WHERE codigo_pais IS NULL
    """)


def downgrade() -> None:
    op.drop_column('clientes', 'codigo_pais')
