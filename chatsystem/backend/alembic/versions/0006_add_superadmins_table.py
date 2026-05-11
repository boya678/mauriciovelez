"""Add public.superadmins table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-11 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "superadmins",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(200), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
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
        "ix_superadmins_email", "superadmins", ["email"], unique=True, schema="public"
    )


def downgrade() -> None:
    op.drop_index("ix_superadmins_email", table_name="superadmins", schema="public")
    op.drop_table("superadmins", schema="public")
