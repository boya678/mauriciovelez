"""create clientes table

Revision ID: 0001
Revises: 
Create Date: 2026-03-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clientes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("nombre", sa.String(150), nullable=False),
        sa.Column("celular", sa.String(30), nullable=False, unique=True),
        sa.Column("correo", sa.String(200), nullable=True),
        sa.Column("cc", sa.String(30), nullable=True),
        sa.Column("saldo", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("vip", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_clientes_celular", "clientes", ["celular"], unique=True)
    op.create_index("ix_clientes_id", "clientes", ["id"])


def downgrade() -> None:
    op.drop_index("ix_clientes_celular", table_name="clientes")
    op.drop_index("ix_clientes_id", table_name="clientes")
    op.drop_table("clientes")
