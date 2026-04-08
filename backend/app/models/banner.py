import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Banner(Base):
    __tablename__ = "banners"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)          # texto | imagen
    texto: Mapped[str | None] = mapped_column(Text(), nullable=True)
    imagen_data: Mapped[bytes | None] = mapped_column(LargeBinary(), nullable=True)
    imagen_mime: Mapped[str | None] = mapped_column(String(50), nullable=True)
    audiencia: Mapped[str] = mapped_column(String(10), nullable=False, default="todos")  # todos | vip
    activo: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fin: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
