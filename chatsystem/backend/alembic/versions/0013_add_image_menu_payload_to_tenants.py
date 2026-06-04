"""Add image_menu_payload to public.tenants.

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-04 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("image_menu_payload", sa.Text(), nullable=True),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("tenants", "image_menu_payload", schema="public")
