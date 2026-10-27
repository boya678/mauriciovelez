"""add tabla_numerologica_foto and tabla_numerologica_entregas tables

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tabla_numerologica_foto",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("imagen_data", sa.LargeBinary(), nullable=False),
        sa.Column("imagen_mime", sa.String(50), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tabla_numerologica_entregas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("celular", sa.String(30), nullable=False),
        sa.Column("message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tabla_numerologica_entregas_created_at", "tabla_numerologica_entregas", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_tabla_numerologica_entregas_created_at", table_name="tabla_numerologica_entregas")
    op.drop_table("tabla_numerologica_entregas")
    op.drop_table("tabla_numerologica_foto")
