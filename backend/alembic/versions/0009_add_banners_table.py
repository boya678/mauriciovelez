"""add banners table

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "banners",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tipo", sa.String(10), nullable=False),          # texto | imagen
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("imagen_data", sa.LargeBinary(), nullable=True),
        sa.Column("imagen_mime", sa.String(50), nullable=True),
        sa.Column("audiencia", sa.String(10), nullable=False, server_default="todos"),  # todos | vip
        sa.Column("activo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fin", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("banners")
