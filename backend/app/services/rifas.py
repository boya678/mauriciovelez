import logging
from datetime import datetime, time, timedelta, timezone
from threading import Thread
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database import SessionLocal

COLOMBIA_TZ = ZoneInfo("America/Bogota")


def _cliente_aplica_rifa(cliente, rifa) -> bool:
    """True si el cliente cumple las condiciones de la rifa."""
    if rifa.solo_vip and not cliente.vip:
        return False
    if rifa.tipos_cliente:  # lista no vacía → filtrar por tipo
        if cliente.tipo_cliente not in rifa.tipos_cliente:
            return False
    return True


def asegurar_pool_numeros_rifa(db: Session, rifa) -> None:
    """Crea (si faltan) los números disponibles de la rifa en rifa_numeros.
    Es idempotente y seguro ante concurrencia (ON CONFLICT DO NOTHING).
    """
    db.execute(
        text(
            """
            INSERT INTO rifa_numeros (rifa_id, numero, orden_aleatorio, asignado)
            SELECT
                CAST(:rifa_id AS uuid),
                base.numero,
                ROW_NUMBER() OVER (ORDER BY random()),
                false
            FROM generate_series(:seq_inicio, :seq_fin) AS base(numero)
            ON CONFLICT (rifa_id, numero) DO NOTHING
            """
        ),
        {
            "rifa_id": str(rifa.id),
            "seq_inicio": int(rifa.seq_inicio),
            "seq_fin": int(rifa.seq_fin),
        },
    )


def _asignar_boletas(db: Session, rifa, cliente_id, suscripcion_id) -> int:
    """Asigna boletas usando el pool rifa_numeros con lock transaccional.
    Retorna la cantidad asignada."""
    from app.models.rifa import Rifa, RifaBoleta, RifaNumero

    # Serializa asignaciones por rifa para evitar colisiones en alta concurrencia.
    db.execute(select(Rifa.id).where(Rifa.id == rifa.id).with_for_update())

    base_query = (
        db.query(RifaNumero)
        .filter(
            RifaNumero.rifa_id == rifa.id,
            RifaNumero.asignado.is_(False),
        )
    )
    candidatas = (
        base_query
        .order_by(RifaNumero.orden_aleatorio)
        .with_for_update(skip_locked=True)
        .limit(rifa.boletas_por_renovacion)
        .all()
    )
    if not candidatas:
        return 0

    now = datetime.now(COLOMBIA_TZ)
    for fila in candidatas:
        fila.asignado = True
        db.add(
            RifaBoleta(
                rifa_id=rifa.id,
                cliente_id=cliente_id,
                suscripcion_id=suscripcion_id,
                numero=fila.numero,
                asignado_en=now,
            )
        )
    db.flush()  # hace visibles los números recién agregados a queries posteriores
    return len(candidatas)


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

    asegurar_pool_numeros_rifa(db, rifa)

    inicio_local = datetime.combine(rifa.fecha_inicio, time.min, tzinfo=COLOMBIA_TZ)
    fin_exclusivo_local = datetime.combine(
        rifa.fecha_fin + timedelta(days=1),
        time.min,
        tzinfo=COLOMBIA_TZ,
    )
    inicio_utc = inicio_local.astimezone(timezone.utc)
    fin_exclusivo_utc = fin_exclusivo_local.astimezone(timezone.utc)

    suscripciones = (
        db.query(Suscripcion, Cliente)
        .join(Cliente, Suscripcion.cliente_id == Cliente.id)
        .filter(
            Suscripcion.created_at >= inicio_utc,
            Suscripcion.created_at < fin_exclusivo_utc,
        )
        .all()
    )

    suscripcion_ids = [sus.id for sus, _ in suscripciones]
    existentes = set()
    if suscripcion_ids:
        existentes = {
            row[0]
            for row in db.query(RifaBoleta.suscripcion_id)
            .filter(
                RifaBoleta.rifa_id == rifa.id,
                RifaBoleta.suscripcion_id.in_(suscripcion_ids),
            )
            .all()
            if row[0] is not None
        }

    total = 0
    for sus, cliente in suscripciones:
        if not _cliente_aplica_rifa(cliente, rifa):
            continue
        if sus.id in existentes:
            continue
        total += _asignar_boletas(db, rifa, cliente.id, sus.id)
    return total


def procesar_rifa_creacion_en_background(rifa_id) -> None:
    """Procesa el pool y el retroactivo fuera de la request HTTP.
    Se usa para devolver respuesta inmediata al usuario.
    """
    db = SessionLocal()
    try:
        from app.models.rifa import Rifa

        rifa = db.get(Rifa, rifa_id)
        if rifa is None:
            logger.warning("No se encontró la rifa %s para procesar en background", rifa_id)
            return

        asegurar_pool_numeros_rifa(db, rifa)
        asignar_boletas_retroactivo(db, rifa)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Error procesando la rifa %s en background", rifa_id)
    finally:
        db.close()


def lanzar_procesamiento_rifa_background(rifa_id) -> None:
    thread = Thread(target=procesar_rifa_creacion_en_background, args=(rifa_id,), daemon=True)
    thread.start()
