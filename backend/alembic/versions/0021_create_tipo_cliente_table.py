"""create tipos_cliente catalog table and add FK from clientes

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-22

tipos_cliente:
  1 = cliente          (registro portal, se le asignan números automáticamente)
  2 = promotor         (creación manual admin, sin números automáticos)
  3 = embajador de oro (antes "aliado", creación manual admin, sin números automáticos)
"""
from alembic import op
import sqlalchemy as sa

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Crear tabla catálogo
    op.create_table(
        'tipos_cliente',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nombre', sa.String(80), nullable=False, unique=True),
        sa.Column('descripcion', sa.String(255), nullable=True),
    )

    # 2. Insertar los tres tipos (aliado renombrado a embajador de oro)
    op.execute("""
        INSERT INTO tipos_cliente (id, nombre, descripcion) VALUES
        (1, 'cliente',          'Registro por portal, recibe números asignados automáticamente'),
        (2, 'promotor',         'Creación manual por admin, sin números automáticos'),
        (3, 'embajador de oro', 'Creación manual por admin, sin números automáticos')
    """)

    # 3. Agregar FK en clientes → tipos_cliente
    op.create_foreign_key(
        'fk_clientes_tipo_cliente',
        'clientes',
        'tipos_cliente',
        ['tipo_cliente'],
        ['id'],
        onupdate='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('fk_clientes_tipo_cliente', 'clientes', type_='foreignkey')
    op.drop_table('tipos_cliente')
