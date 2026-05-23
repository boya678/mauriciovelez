"""add ciudad barrio departamento to clientes and create seq_embajador_codigo

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-22
"""
from alembic import op
import sqlalchemy as sa

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('clientes', sa.Column('departamento', sa.String(100), nullable=True))
    op.add_column('clientes', sa.Column('ciudad',       sa.String(100), nullable=True))
    op.add_column('clientes', sa.Column('barrio',       sa.String(100), nullable=True))
    op.execute("CREATE SEQUENCE seq_embajador_codigo START 1")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS seq_embajador_codigo")
    op.drop_column('clientes', 'barrio')
    op.drop_column('clientes', 'ciudad')
    op.drop_column('clientes', 'departamento')
