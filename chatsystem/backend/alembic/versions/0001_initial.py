"""Create public.tenants table.

Revision ID: 0001
Revises: 
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS public')

    op.create_table(
        "tenants",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("slug", sa.String(60), nullable=False, unique=True),
        sa.Column("schema_name", sa.String(70), nullable=False, unique=True),
        sa.Column("whatsapp_phone_id", sa.String(60), nullable=True),
        sa.Column("whatsapp_token", sa.Text, nullable=True),
        sa.Column("webhook_secret", sa.String(200), nullable=True),
        sa.Column("meta_app_secret", sa.String(200), nullable=True),
        sa.Column("ai_system_prompt", sa.Text, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="public",
    )
    op.create_index(
        "ix_tenants_slug", "tenants", ["slug"], unique=True, schema="public"
    )


def downgrade() -> None:
    op.drop_index("ix_tenants_slug", table_name="tenants", schema="public")
    op.drop_table("tenants", schema="public")
