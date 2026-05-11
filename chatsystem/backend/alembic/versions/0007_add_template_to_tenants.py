"""Add whatsapp_template fields to public.tenants.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-11 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("whatsapp_template_name", sa.String(200), nullable=True),
        schema="public",
    )
    op.add_column(
        "tenants",
        sa.Column(
            "whatsapp_template_language",
            sa.String(20),
            nullable=True,
            server_default="es",
        ),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("tenants", "whatsapp_template_language", schema="public")
    op.drop_column("tenants", "whatsapp_template_name", schema="public")
