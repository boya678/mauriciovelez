"""add zona and video_url to banners

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "banners",
        sa.Column(
            "zona",
            sa.String(10),
            nullable=False,
            server_default="portal",
        ),
    )
    op.add_column(
        "banners",
        sa.Column("video_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("banners", "video_url")
    op.drop_column("banners", "zona")
