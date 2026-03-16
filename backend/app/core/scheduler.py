import logging
import uuid
from datetime import date, datetime, timezone

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

from app.database import SessionLocal
from app.models.cliente import Cliente
from app.models.loteria_resultado import LoteriaResultado
from app.models.numero_acierto import NumeroAcierto
from app.models.numbers_historic import NumberHistoric
from app.models.suscripcion import Suscripcion

COLOMBIA_TZ = ZoneInfo("America/Bogota")
LOTERIAS_API = "https://api-resultadosloterias.com/api/results"

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler(timezone="UTC")


def _clasificar(numero: str, resultado: str) -> list[str]:
    """
    Devuelve una lista con los tipos de acierto que aplican entre `numero` y `resultado`.
    - exacto: los 4 dígitos coinciden
    - tres_orden: los últimos 3 dígitos coinciden en orden
    - tres_desorden: los últimos 3 dígitos son los mismos sin importar el orden
    """
    tipos: list[str] = []
    n4 = numero.zfill(4)[-4:]
    r4 = resultado.zfill(4)[-4:]
    if n4 == r4:
        tipos.append("exacto")
        return tipos  # exacto ya incluye los otros
    n3 = n4[-3:]
    r3 = r4[-3:]
    if n3 == r3:
        tipos.append("tres_orden")
    elif sorted(n3) == sorted(r3):
        tipos.append("tres_desorden")
    return tipos


def _procesar_loterias(fecha: date | None = None) -> None:
    """
    1. Obtiene resultados de la API externa para `fecha` (hoy en Colombia si None).
    2. Hace upsert en loteria_resultados.
    3. Cruza con numbers_historic del mismo día y registra en numero_aciertos.
    """
    hoy_col = fecha or datetime.now(COLOMBIA_TZ).date()
    fecha_str = hoy_col.strftime("%Y-%m-%d")
    logger.info("Procesando loterias para %s", fecha_str)

    db = SessionLocal()
    try:
        # ── 1. Fetch API externa ──────────────────────────────────────────────
        try:
            resp = httpx.get(f"{LOTERIAS_API}/{fecha_str}", timeout=15)
            resp.raise_for_status()
            data = resp.json().get("data", [])
        except Exception:
            logger.exception("Error al consultar API loterias para %s", fecha_str)
            return

        if not data:
            logger.info("Sin resultados de loterias para %s", fecha_str)
            return

        # ── 2. Upsert resultados ──────────────────────────────────────────────
        resultados_map: dict[str, LoteriaResultado] = {}
        for item in data:
            slug = item.get("slug", "")
            existing = (
                db.query(LoteriaResultado)
                .filter(LoteriaResultado.fecha == hoy_col, LoteriaResultado.slug == slug)
                .first()
            )
            if existing:
                existing.resultado = item.get("result", "")
                existing.fetched_at = datetime.now(timezone.utc)
                resultados_map[slug] = existing
            else:
                nuevo = LoteriaResultado(
                    id=uuid.uuid4(),
                    fecha=hoy_col,
                    loteria=item.get("lottery", slug),
                    slug=slug,
                    resultado=item.get("result", ""),
                    serie=item.get("series", ""),
                    fetched_at=datetime.now(timezone.utc),
                )
                db.add(nuevo)
                resultados_map[slug] = nuevo

        db.flush()

        # ── 3. Cruce con numbers_historic ─────────────────────────────────────
        historicos = (
            db.query(NumberHistoric)
            .filter(NumberHistoric.date == hoy_col)
            .all()
        )

        nuevos_aciertos = 0
        for h in historicos:
            for resultado in resultados_map.values():
                for tipo in _clasificar(h.number, resultado.resultado):
                    existe = (
                        db.query(NumeroAcierto)
                        .filter(
                            NumeroAcierto.historic_id == h.id,
                            NumeroAcierto.resultado_id == resultado.id,
                            NumeroAcierto.tipo == tipo,
                        )
                        .first()
                    )
                    if not existe:
                        db.add(NumeroAcierto(
                            id=uuid.uuid4(),
                            historic_id=h.id,
                            resultado_id=resultado.id,
                            tipo=tipo,
                        ))
                        nuevos_aciertos += 1

        db.commit()
        logger.info(
            "Loterias %s: %d resultados, %d historicos, %d nuevos aciertos",
            fecha_str, len(data), len(historicos), nuevos_aciertos,
        )
    except Exception:
        db.rollback()
        logger.exception("Error en _procesar_loterias para %s", fecha_str)
    finally:
        db.close()


def _desactivar_vip_vencidos() -> None:
    """
    Marca como vip=False a todos los clientes cuya suscripción activa
    haya vencido y que no tengan otra suscripción vigente.
    También marca activa=False las suscripciones vencidas.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # 1. Marcar suscripciones vencidas
        vencidas = (
            db.query(Suscripcion)
            .filter(Suscripcion.activa == True, Suscripcion.fin < now)
            .all()
        )
        for s in vencidas:
            s.activa = False

        # 2. Identificar clientes VIP sin ninguna suscripción vigente
        subquery = (
            db.query(Suscripcion.cliente_id)
            .filter(Suscripcion.activa == True, Suscripcion.fin >= now)
            .subquery()
        )
        expirados = (
            db.query(Cliente)
            .filter(Cliente.vip == True, ~Cliente.id.in_(subquery))
            .all()
        )
        for c in expirados:
            c.vip = False
            logger.info("VIP desactivado: %s (%s)", c.nombre, c.celular)

        db.commit()
        logger.info(
            "Cron vip_check: %d suscripciones vencidas, %d clientes desactivados",
            len(vencidas),
            len(expirados),
        )
    except Exception:
        db.rollback()
        logger.exception("Error en cron _desactivar_vip_vencidos")
    finally:
        db.close()


def start() -> None:
    """Registra los jobs y arranca el scheduler."""
    _scheduler.add_job(
        _desactivar_vip_vencidos,
        trigger=CronTrigger(hour=3, minute=0, timezone="UTC"),
        id="vip_check",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Procesar loterias 4 veces al día en hora Colombia (UTC-5)
    # 10:00 COT = 15:00 UTC | 14:00 COT = 19:00 UTC | 18:00 COT = 23:00 UTC | 23:30 COT = 04:30 UTC
    for job_id, (h, m) in [
        ("loterias_1000", (15, 0)),
        ("loterias_1400", (19, 0)),
        ("loterias_1800", (23, 0)),
        ("loterias_2330", (4, 30)),
    ]:
        _scheduler.add_job(
            _procesar_loterias,
            trigger=CronTrigger(hour=h, minute=m, timezone="UTC"),
            id=job_id,
            replace_existing=True,
            misfire_grace_time=3600,
        )
    _scheduler.start()
    logger.info("Scheduler iniciado — vip_check 03:00 UTC + loterias 4x/día")


def stop() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido")
