import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Integer, Numeric, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.database import Base

ACUMULADO_POR_EVENTO = Decimal("500.00")


class CuentaVip(Base):
    __tablename__ = "cuentas_vip"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("anio", "mes", name="uq_cuenta_vip_anio_mes"),)


def acumular_cuenta_vip(db: Session) -> None:
    """Suma 500 al registro de cuentas_vip del mes/año actual. Crea la fila si no existe."""
    now = datetime.now(timezone.utc)
    fila = (
        db.query(CuentaVip)
        .filter(CuentaVip.anio == now.year, CuentaVip.mes == now.month)
        .first()
    )
    if fila:
        fila.total += ACUMULADO_POR_EVENTO
        fila.updated_at = now
    else:
        db.add(CuentaVip(
            anio=now.year,
            mes=now.month,
            total=ACUMULADO_POR_EVENTO,
            updated_at=now,
        ))
