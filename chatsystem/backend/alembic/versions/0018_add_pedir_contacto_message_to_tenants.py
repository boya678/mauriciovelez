"""Add pedir_contacto_template to public.tenants.

Stores the name of the Meta-approved WhatsApp template used by the
pedir_contacto utility.  When set, send_template_message() is called
with this template name instead of the default request_contact_info
interactive message.

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("pedir_contacto_template", sa.String(200), nullable=True),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("tenants", "pedir_contacto_template", schema="public")
