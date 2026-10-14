"""Servicio 'número relámpago personalizado': número pago asignado a un celular."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cliente import Cliente
from app.models.numbers_users import NumberUser
from app.services.notification_queue import push
from app.services.numbers import assign_number


def asignar_relampago_personalizado(
    db: Session, celular_local: str, vigencia_dias: int,
) -> tuple[Cliente, NumberUser]:
    """Asigna un número relámpago al celular; si no existe lo crea como cliente básico
    (nombre = celular, no VIP). Hace flush pero NO commit."""
    cliente = db.execute(
        select(Cliente).where(Cliente.celular == celular_local)
    ).scalar_one_or_none()

    if cliente is None:
        cliente = Cliente(
            id=uuid.uuid4(),
            nombre=celular_local,
            celular=celular_local,
            codigo_pais="57",
            tipo_cliente=1,
            saldo=0,
        )
        db.add(cliente)
        db.flush()

    return cliente, assign_number(db, cliente.id, "relampago", vigencia_dias=vigencia_dias)


def notificar_relampago_personalizado(celular_wp: str, numero: str) -> None:
    """Encola el aviso con el número y su método (misma plantilla WHATSAPP_NOTIFICAR_RELAMPAGO)."""
    if not settings.WHATSAPP_NOTIFICAR_RELAMPAGO:
        return
    metodo = numero[:-3] + numero[-3:][::-1] if len(numero) >= 3 else numero[::-1]
    push("notificar_relampago", celular_wp, {"texto": f"{numero} - {metodo}"})
