import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MensajeIaProcesado(Base):
    """Registra qué mensajes del chat DB ya fueron analizados por la IA.
    Evita reprocesar la misma imagen indefinidamente.
    """
    __tablename__ = "mensajes_ia_procesados"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # ID del mensaje en la BD de chat (t_mauriciovelez.messages.id)
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    es_comprobante: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    monto_extraido: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    comprobante_num: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    image_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    numero_destino: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    nombre_destino: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    destino_valido: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
