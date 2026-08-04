"""Rename pedir_contacto_message → pedir_contacto_template in public.tenants.

Migration 0018 created the column as 'pedir_contacto_message' (text body).
The design changed: it now stores the Meta template name instead of a
free-form message text, so we rename + change type to VARCHAR(200).

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Column may exist as pedir_contacto_message (old name) or not at all
    # if 0018 ran the updated version that already used the new name.
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='tenants' "
            "AND column_name='pedir_contacto_message'"
        )
    ).fetchone()

    if row:
        op.alter_column(
            "tenants",
            "pedir_contacto_message",
            new_column_name="pedir_contacto_template",
            schema="public",
            type_=sa.String(200),
        )
    else:
        # Column was never created (or already renamed) — add it directly
        op.add_column(
            "tenants",
            sa.Column("pedir_contacto_template", sa.String(200), nullable=True),
            schema="public",
        )


def downgrade() -> None:
    op.alter_column(
        "tenants",
        "pedir_contacto_template",
        new_column_name="pedir_contacto_message",
        schema="public",
        type_=sa.Text,
    )
