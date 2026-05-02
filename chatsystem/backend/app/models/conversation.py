import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

import enum


class ConversationStatus(str, enum.Enum):
    NEW = "new"
    BOT_ACTIVE = "bot_active"
    WAITING_HUMAN = "waiting_human"
    HUMAN_ACTIVE = "human_active"
    CLOSED = "closed"


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conv_phone", "phone"),
        Index("ix_conv_status", "status"),
        Index("ix_conv_agent", "assigned_agent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=ConversationStatus.NEW.value,
    )
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
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
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
