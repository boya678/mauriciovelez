import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ComprobanteVip(Base):
    """Registro maestro de comprobantes de pago VIP procesados.
    Dos restricciones UNIQUE independientes:
    - comprobante_num: mismo número de comprobante no se repite
    - image_hash: misma imagen física no se repite aunque la IA lea diferente
    """
    __tablename__ = "comprobantes_vip"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    comprobante_num: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True, index=True
    )
    celular: Mapped[str] = mapped_column(String(30), nullable=False)
    monto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(300), nullable=False, default="pago vip")
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    image_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
