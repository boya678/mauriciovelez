"""create referidos table

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'referidos',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'referente_id',
            UUID(as_uuid=True),
            sa.ForeignKey('clientes.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'referido_id',
            UUID(as_uuid=True),
            sa.ForeignKey('clientes.id', ondelete='CASCADE'),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            'fecha_registro',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index('ix_referidos_referente_id', 'referidos', ['referente_id'])
    op.create_index('ix_referidos_referido_id', 'referidos', ['referido_id'])


def downgrade() -> None:
    op.drop_table('referidos')
