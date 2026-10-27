import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TablaNumerologicaFoto(Base):
    """Foto única (id=1) que se envía en el servicio 'Tabla numerológica'."""
    __tablename__ = "tabla_numerologica_foto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    imagen_data: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    imagen_mime: Mapped[str] = mapped_column(String(50), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class TablaNumerologicaEntrega(Base):
    """Registro de cada foto entregada por el servicio 'Tabla numerológica'."""
    __tablename__ = "tabla_numerologica_entregas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    celular: Mapped[str] = mapped_column(String(30), nullable=False)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
