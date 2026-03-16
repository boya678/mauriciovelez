"""add loteria_resultados table

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "loteria_resultados",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("loteria", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("resultado", sa.String(10), nullable=False),
        sa.Column("serie", sa.String(20), nullable=False, server_default=""),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_loteria_resultados_fecha", "loteria_resultados", ["fecha"])
    op.create_unique_constraint("uq_loteria_fecha_slug", "loteria_resultados", ["fecha", "slug"])


def downgrade() -> None:
    op.drop_table("loteria_resultados")
