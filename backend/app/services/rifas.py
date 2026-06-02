import random
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import cast, Date
from sqlalchemy.orm import Session

COLOMBIA_TZ = ZoneInfo("America/Bogota")


def _cliente_aplica_rifa(cliente, rifa) -> bool:
    """True si el cliente cumple las condiciones de la rifa."""
    if rifa.solo_vip and not cliente.vip:
        return False
    if rifa.tipos_cliente:  # lista no vacía → filtrar por tipo
        if cliente.tipo_cliente not in rifa.tipos_cliente:
            return False
    return True


def _asignar_boletas(db: Session, rifa, cliente_id, suscripcion_id) -> int:
    """Asigna boletas_por_renovacion números aleatorios únicos dentro del rango.
    Retorna la cantidad asignada."""
    from app.models.rifa import RifaBoleta

    usados = set(
        row[0]
        for row in db.query(RifaBoleta.numero)
        .filter(RifaBoleta.rifa_id == rifa.id)
        .all()
    )
    disponibles = list(set(range(rifa.seq_inicio, rifa.seq_fin + 1)) - usados)
    cantidad = min(rifa.boletas_por_renovacion, len(disponibles))
    if cantidad == 0:
        return 0

    seleccionados = random.sample(disponibles, cantidad)
    now = datetime.now(COLOMBIA_TZ)
    for num in seleccionados:
        db.add(
            RifaBoleta(
                rifa_id=rifa.id,
                cliente_id=cliente_id,
                suscripcion_id=suscripcion_id,
                numero=num,
                asignado_en=now,
            )
        )
    return cantidad


def asignar_boletas_por_suscripcion(db: Session, cliente, suscripcion_id) -> int:
    """Hook llamado en cada renovación.
    Busca la rifa activa del día, verifica condiciones del cliente y asigna boletas.
    """
    from app.models.rifa import Rifa

    today = datetime.now(COLOMBIA_TZ).date()
    rifa = (
        db.query(Rifa)
        .filter(
            Rifa.estado == "activa",
            Rifa.fecha_inicio <= today,
            Rifa.fecha_fin >= today,
        )
        .first()
    )
    if not rifa:
        return 0
    if not _cliente_aplica_rifa(cliente, rifa):
        return 0
    return _asignar_boletas(db, rifa, cliente.id, suscripcion_id)


def asignar_boletas_retroactivo(db: Session, rifa) -> int:
    """Llamado al crear una rifa nueva.
    Para cada suscripción cuyo inicio caiga en el período de la rifa, asigna boletas
    (una vez por suscripción, si el cliente aplica).
    Retorna el total de boletas asignadas.
    """
    from app.models.rifa import RifaBoleta
    from app.models.suscripcion import Suscripcion
    from app.models.cliente import Cliente

    suscripciones = (
        db.query(Suscripcion, Cliente)
        .join(Cliente, Suscripcion.cliente_id == Cliente.id)
        .filter(
            cast(Suscripcion.inicio, Date) >= rifa.fecha_inicio,
            cast(Suscripcion.inicio, Date) <= rifa.fecha_fin,
        )
        .all()
    )

    total = 0
    for sus, cliente in suscripciones:
        if not _cliente_aplica_rifa(cliente, rifa):
            continue
        # Evitar doble asignación por la misma suscripción
        ya = (
            db.query(RifaBoleta)
            .filter(
                RifaBoleta.rifa_id == rifa.id,
                RifaBoleta.suscripcion_id == sus.id,
            )
            .first()
        )
        if ya:
            continue
        total += _asignar_boletas(db, rifa, cliente.id, sus.id)
    return total
