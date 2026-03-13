"""create numbers_users table

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "numbers_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("number", sa.String(), nullable=False),
        sa.Column("id_user", UUID(as_uuid=True), nullable=False),
        sa.Column("date_assigned", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("type", sa.String(10), nullable=False, server_default="free"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["id_user"], ["clientes.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_numbers_users_id_user", "numbers_users", ["id_user"])
    op.create_index("ix_numbers_users_id_user_type", "numbers_users", ["id_user", "type"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_numbers_users_id_user_type", "numbers_users")
    op.drop_index("ix_numbers_users_id_user", "numbers_users")
    op.drop_table("numbers_users")
