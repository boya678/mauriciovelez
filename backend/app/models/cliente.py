import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    celular: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)
    correo: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    cc: Mapped[str | None] = mapped_column(String(30), nullable=True, default=None)
    saldo: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    vip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    codigo_vip: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
