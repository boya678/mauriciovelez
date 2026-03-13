import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PlatformUser(Base):
    __tablename__ = "platform_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cc: Mapped[str] = mapped_column(String(30), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    usuario: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    clave: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # admin | edit | reader
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
