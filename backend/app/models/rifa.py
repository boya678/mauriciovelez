import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Rifa(Base):
    __tablename__ = "rifas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text(), nullable=True)
    imagen_data: Mapped[bytes | None] = mapped_column(LargeBinary(), nullable=True)
    imagen_mime: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fecha_inicio: Mapped[date] = mapped_column(Date(), nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date(), nullable=False)
    seq_inicio: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    seq_fin: Mapped[int] = mapped_column(Integer(), nullable=False, default=9999)
    boletas_por_renovacion: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    solo_vip: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    tipos_cliente: Mapped[list] = mapped_column(JSONB(), nullable=False, default=list)
    ganador_numero: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="activa")  # activa | finalizada
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class RifaBoleta(Base):
    __tablename__ = "rifa_boletas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rifa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rifas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suscripcion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suscripciones.id", ondelete="SET NULL"), nullable=True
    )
    numero: Mapped[int] = mapped_column(Integer(), nullable=False)
    asignado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    rifa = relationship("Rifa", backref="boletas")
    cliente = relationship("Cliente", backref="rifa_boletas")
