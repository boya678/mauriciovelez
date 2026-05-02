import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ToolType(str, enum.Enum):
    HTTP = "HTTP"
    SQL = "SQL"
    STATIC = "STATIC"


class AgentTool(Base):
    """Lives in public schema — shared across all tenants."""
    __tablename__ = "agent_tools"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tool_type: Mapped[ToolType] = mapped_column(
        Enum(ToolType, name="tool_type", create_constraint=False),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── HTTP ──────────────────────────────────────────────────────────────────
    http_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_method: Mapped[str | None] = mapped_column(String(10), nullable=True, default="GET")
    http_headers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    http_body_tpl: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True, default=10)

    # ── SQL ───────────────────────────────────────────────────────────────────
    sql_dsn: Mapped[str | None] = mapped_column(Text, nullable=True)
    sql_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    # list of parameter names the LLM must supply, e.g. ["phone"]
    sql_params: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ── STATIC ────────────────────────────────────────────────────────────────
    static_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
