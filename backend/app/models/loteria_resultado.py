import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LoteriaResultado(Base):
    __tablename__ = "loteria_resultados"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    loteria: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    resultado: Mapped[str] = mapped_column(String(10), nullable=False)
    serie: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (UniqueConstraint("fecha", "slug", name="uq_loteria_fecha_slug"),)
