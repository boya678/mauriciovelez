"""allow several relampago numbers per client in numbers_users

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_numbers_users_id_user_type", table_name="numbers_users")
    op.create_index(
        "ix_numbers_users_id_user_type",
        "numbers_users",
        ["id_user", "type"],
        unique=True,
        postgresql_where=sa.text("type <> 'relampago'"),
    )


def downgrade() -> None:
    # El índice único completo no admite varios relampago por cliente.
    op.execute("DELETE FROM numbers_users WHERE type = 'relampago'")
    op.drop_index("ix_numbers_users_id_user_type", table_name="numbers_users")
    op.create_index("ix_numbers_users_id_user_type", "numbers_users", ["id_user", "type"], unique=True)
