"""add numero_aciertos table

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "numero_aciertos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "historic_id",
            sa.Integer(),
            sa.ForeignKey("numbers_historic.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resultado_id",
            UUID(as_uuid=True),
            sa.ForeignKey("loteria_resultados.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_numero_aciertos_historic_id", "numero_aciertos", ["historic_id"])
    op.create_unique_constraint(
        "uq_acierto_historic_resultado_tipo",
        "numero_aciertos",
        ["historic_id", "resultado_id", "tipo"],
    )


def downgrade() -> None:
    op.drop_table("numero_aciertos")
