from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class RifaEnumeradaBase(Base):
    """Imagen base de la boleta (fila única id=1)."""
    __tablename__ = "rifa_enum_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    imagen_data: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    imagen_mime: Mapped[str] = mapped_column(String(50), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_ahora, onupdate=_ahora)


class RifaEnumeradaNumero(Base):
    """Los números 0000-9999 en el orden barajado en que se entregan."""
    __tablename__ = "rifa_enum_numeros"

    numero: Mapped[str] = mapped_column(String(4), primary_key=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, index=True)


class RifaEnumeradaLote(Base):
    """Un Excel cargado; se envía cuando el admin pulsa Enviar."""
    __tablename__ = "rifa_enum_lotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_ahora)
    usuario: Mapped[str] = mapped_column(String(100), nullable=False)
    archivo: Mapped[str] = mapped_column(String(200), nullable=False)
    celulares: Mapped[str] = mapped_column(Text, nullable=False)  # uno por línea, con 57
    total_filas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalidas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalidas_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(String(12), nullable=False, default="cargado")  # cargado | enviando | finalizado
    incluir_repetidos: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cantidad: Mapped[int | None] = mapped_column(Integer, nullable=True)
    iniciado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalizado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RifaEnumeradaAviso(Base):
    """Aviso 'boletas listas' enviado a un celular; las boletas se entregan cuando pulsa SOLICITAR BOLETAS."""
    __tablename__ = "rifa_enum_avisos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lote_id: Mapped[int] = mapped_column(Integer, ForeignKey("rifa_enum_lotes.id", ondelete="CASCADE"), nullable=False, index=True)
    celular: Mapped[str] = mapped_column(String(20), nullable=False)
    celular_local: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    estado: Mapped[str] = mapped_column(String(10), nullable=False, default="pendiente")  # pendiente | enviado | error
    wamid: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    enviado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    solicitada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_ahora)


class RifaEnumeradaBoleta(Base):
    """Una boleta entregada a un celular: qué número, si se envió y si se pagó."""
    __tablename__ = "rifa_enum_boletas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lote_id: Mapped[int] = mapped_column(Integer, ForeignKey("rifa_enum_lotes.id", ondelete="CASCADE"), nullable=False)
    aviso_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("rifa_enum_avisos.id", ondelete="SET NULL"), nullable=True, index=True)
    celular: Mapped[str] = mapped_column(String(20), nullable=False)
    celular_local: Mapped[str] = mapped_column(String(10), nullable=False)
    numero: Mapped[str] = mapped_column(String(4), nullable=False)
    ronda: Mapped[int] = mapped_column(Integer, nullable=False)
    estado_envio: Mapped[str] = mapped_column(String(12), nullable=False, default="pendiente")  # pendiente | enviada | error
    wamid: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    enviada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pagada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pagada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comprobante_num: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pago_monto: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    retirada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retirada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retirada_por: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_ahora)
