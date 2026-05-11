"""add tipo_cliente to clientes

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-01

tipo_cliente:
  1 = cliente  (registro portal, se le asignan números)
  2 = promotor (creación manual admin, sin números automáticos)
  3 = aliado   (creación manual admin, sin números automáticos)
"""
from alembic import op
import sqlalchemy as sa

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'clientes',
        sa.Column('tipo_cliente', sa.Integer(), nullable=False, server_default='1'),
    )


def downgrade() -> None:
    op.drop_column('clientes', 'tipo_cliente')
