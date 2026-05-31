"""create seq_vip_codigo for tipo_cliente=1

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-29
"""
from alembic import op

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE seq_vip_codigo START 5697")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS seq_vip_codigo")
