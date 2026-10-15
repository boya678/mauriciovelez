"""Servicio 'número relámpago personalizado': número pago y, opcionalmente, número de rifa."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cliente import Cliente
from app.models.numero_rifa_entregado import NumeroRifaEntregado
from app.models.numbers_users import NumberUser
from app.models.parametro import Parametro
from app.services.notification_queue import push
from app.services.numbers import assign_number
from app.services.servicios_config import KEY_RP_RIFA_SIGUIENTE, RelampagoPersonalizadoConfig

RIFA_TOTAL = 10000  # números 0000-9999


def _siguiente_numero_rifa(db: Session) -> str:
    """Entrega el siguiente 0000-9999 y reinicia en 0000 al terminar. Bloquea el contador."""
    contador = db.execute(
        select(Parametro).where(Parametro.clave == KEY_RP_RIFA_SIGUIENTE).with_for_update()
    ).scalar_one()
    actual = int(contador.valor) % RIFA_TOTAL
    contador.valor = str((actual + 1) % RIFA_TOTAL)
    return f"{actual:04d}"


def asignar_relampago_personalizado(
    db: Session, celular_local: str, cfg: RelampagoPersonalizadoConfig, message_id: uuid.UUID | None = None,
) -> tuple[Cliente, NumberUser, NumeroRifaEntregado | None]:
    """Asigna el número relámpago (y el de rifa si está activo) al celular; si no existe
    lo crea como cliente básico (nombre = celular, no VIP). Hace flush pero NO commit."""
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

    asignacion = assign_number(db, cliente.id, "relampago", vigencia_dias=cfg.vigencia_dias)

    rifa = None
    if cfg.rifa_activo:
        rifa = NumeroRifaEntregado(
            numero=_siguiente_numero_rifa(db),
            cliente_id=cliente.id,
            celular=celular_local,
            descripcion=cfg.rifa_descripcion,
            message_id=message_id,
        )
        db.add(rifa)
        db.flush()

    return cliente, asignacion, rifa


def notificar_relampago_personalizado(
    celular_wp: str, numero: str, rifa: NumeroRifaEntregado | None = None,
) -> None:
    """Encola el aviso del número relámpago y, si hay, el del número de rifa."""
    if settings.WHATSAPP_NOTIFICAR_PERSONALIZADO:
        metodo = numero[:-3] + numero[-3:][::-1] if len(numero) >= 3 else numero[::-1]
        push("notificar_relampago_personalizado", celular_wp, {"texto": f"{numero} - {metodo}"})
    if rifa is not None:
        push("notificar_numero_rifa", celular_wp, {"numero": rifa.numero, "descripcion": rifa.descripcion})
