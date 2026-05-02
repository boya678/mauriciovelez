import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

import enum


class SenderType(str, enum.Enum):
    USER = "user"
    BOT = "bot"
    HUMAN = "human"


class MessageStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    ERROR = "error"


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_msg_conversation", "conversation_id"),
        UniqueConstraint("external_id", name="uq_msg_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    sender_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(30), nullable=False, default="text")
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MessageStatus.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
