"""Alter tenants.id from VARCHAR to UUID.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-30 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Alter VARCHAR(36) column to native UUID type (no extension needed in PG13+)
    op.execute("""
        ALTER TABLE public.tenants
            ALTER COLUMN id TYPE UUID USING id::uuid
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE public.tenants
            ALTER COLUMN id TYPE VARCHAR(36) USING id::text
    """)
