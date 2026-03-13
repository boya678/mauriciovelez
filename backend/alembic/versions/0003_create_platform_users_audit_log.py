"""create platform_users, audit_log and seed admin user

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-12
"""
import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── platform_users ──────────────────────────────────────────────────────────
    op.create_table(
        "platform_users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("cc", sa.String(30), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("usuario", sa.String(60), nullable=False),
        sa.Column("clave", sa.String(200), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("usuario", name="uq_platform_users_usuario"),
    )

    # ── audit_log ───────────────────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True, nullable=False),
        sa.Column("platform_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("usuario", sa.String(60), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("entity", sa.String(60), nullable=False),
        sa.Column("entity_id", sa.String(60), nullable=True),
        sa.Column("detail", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["platform_user_id"],
            ["platform_users.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_audit_log_platform_user_id", "audit_log", ["platform_user_id"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    # ── seed: usuario admin base ─────────────────────────────────────────────────
    # Usamos bcrypt directamente (passlib 1.7.4 no es compatible con bcrypt 5.x)
    import bcrypt as _bcrypt  # noqa: PLC0415

    admin_id = str(uuid.uuid4())
    hashed = _bcrypt.hashpw("Admin1234*".encode(), _bcrypt.gensalt()).decode()

    op.execute(
        sa.text(
            """
            INSERT INTO platform_users (id, cc, nombre, usuario, clave, role, active)
            SELECT :id, :cc, :nombre, :usuario, :clave, :role, true
            WHERE NOT EXISTS (
                SELECT 1 FROM platform_users WHERE usuario = :usuario
            )
            """
        ).bindparams(
            id=admin_id,
            cc="0000000000",
            nombre="Administrador",
            usuario="admin",
            clave=hashed,
            role="admin",
        )
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_created_at", "audit_log")
    op.drop_index("ix_audit_log_platform_user_id", "audit_log")
    op.drop_table("audit_log")
    op.drop_table("platform_users")
