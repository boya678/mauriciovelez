import logging
import uuid
from datetime import date, datetime, timezone

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.database import SessionLocal
from app.models.cliente import Cliente
from app.models.loteria_resultado import LoteriaResultado
from app.models.numero_acierto import NumeroAcierto
from app.models.numbers_historic import NumberHistoric
from app.models.numbers_users import NumberUser
from app.models.suscripcion import Suscripcion
from app.services.numbers import assign_number, VIGENCIA_FREE, VIGENCIA_VIP

COLOMBIA_TZ = ZoneInfo("America/Bogota")
LOTERIAS_API = "https://api-resultadosloterias.com/api/results"

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler(timezone="UTC")


def _clasificar(numero: str, resultado: str) -> list[str]:
    """
    Devuelve los tipos de acierto (máximo uno, el de mayor jerarquía):
    - exacto:           los 4 dígitos coinciden exactamente
    - directo_devuelto: primer dígito igual + últimos 3 en orden inverso (3267 vs 3762)
    - tres_orden:       últimos 3 dígitos iguales en orden (sin importar el primero)
    - tres_desorden:    últimos 3 dígitos en orden inverso (sin importar el primero)
    """
    n4 = numero.zfill(4)[-4:]
    r4 = resultado.zfill(4)[-4:]
    n3 = n4[-3:]
    r3 = r4[-3:]
    r3_rev = r3[::-1]

    if n4 == r4:
        return ["exacto"]
    if n4[0] == r4[0] and n3 == r3_rev:
        return ["directo_devuelto"]
    if n3 == r3:
        return ["tres_orden"]
    if n3 == r3_rev:
        return ["tres_desorden"]
    return []


def _notificar_nuevo_numero_vip(celular: str, numero: str, valid_until: date) -> None:
    """Envía WhatsApp al cliente VIP cuando se le asigna un número nuevo."""
    numero_dest = celular if celular.startswith('57') else f'57{celular}'
    url = f'https://graph.facebook.com/v25.0/{settings.WHATSAPP_PHONE_ID}/messages'
    headers = {
        'Authorization': f'Bearer {settings.WHATSAPP_TOKEN}',
        'Content-Type': 'application/json',
    }
    body = {
        'messaging_product': 'whatsapp',
        'to': numero_dest,
        'type': 'template',
        'template': {
            'name': settings.WHATSAPP_TEMPLATE_NOTIFICACION_NUMERO_VIP,
            'language': {'code': 'es_CO'},
            'components': [
                {
                    'type': 'body',
                    'parameters': [
                        {'type': 'text', 'text': numero},
                        {'type': 'text', 'text': valid_until.strftime('%d/%m/%Y')},
                    ],
                },
            ],
        },
    }
    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=10)
        if resp.status_code >= 400:
            logger.warning("WhatsApp nuevo_numero_vip falló (%s): %s", resp.status_code, resp.text)
    except Exception:
        logger.exception("Error al enviar WhatsApp nuevo_numero_vip a %s", celular)


def _notificar_ganador_free(celular: str, numero: str, loteria: str, resultado_num: str, tipo: str) -> None:
    """Envía WhatsApp al cliente free ganador usando la template configurada."""
    numero_dest = celular if celular.startswith('57') else f'57{celular}'
    url = f'https://graph.facebook.com/v25.0/{settings.WHATSAPP_PHONE_ID}/messages'
    headers = {
        'Authorization': f'Bearer {settings.WHATSAPP_TOKEN}',
        'Content-Type': 'application/json',
    }
    body = {
        'messaging_product': 'whatsapp',
        'to': numero_dest,
        'type': 'template',
        'template': {
            'name': settings.WHATSAPP_TEMPLATE_GANADOR_FREE,
            'language': {'code': 'es_CO'},
            'components': [
                {
                    'type': 'body',
                    'parameters': [
                        {'type': 'text', 'text': numero},
                        {'type': 'text', 'text': f'{loteria} {resultado_num} {tipo}'},
                    ],
                },
            ],
        },
    }
    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=10)
        if resp.status_code >= 400:
            logger.warning("WhatsApp ganador_free falló (%s): %s", resp.status_code, resp.text)
    except Exception:
        logger.exception("Error al enviar WhatsApp ganador_free a %s", celular)


def _notificar_ganador_vip(celular: str, numero: str, loteria: str, resultado_num: str, tipo: str) -> None:
    """Envía WhatsApp al cliente VIP ganador (sin deshabilitar la cuenta)."""
    numero_dest = celular if celular.startswith('57') else f'57{celular}'
    url = f'https://graph.facebook.com/v25.0/{settings.WHATSAPP_PHONE_ID}/messages'
    headers = {
        'Authorization': f'Bearer {settings.WHATSAPP_TOKEN}',
        'Content-Type': 'application/json',
    }
    body = {
        'messaging_product': 'whatsapp',
        'to': numero_dest,
        'type': 'template',
        'template': {
            'name': settings.WHATSAPP_TEMPLATE_GANADOR_VIP,
            'language': {'code': 'es_CO'},
            'components': [
                {
                    'type': 'body',
                    'parameters': [
                        {'type': 'text', 'text': numero},
                        {'type': 'text', 'text': f'{loteria} {resultado_num} {tipo}'},
                    ],
                },
            ],
        },
    }
    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=10)
        if resp.status_code >= 400:
            logger.warning("WhatsApp ganador_vip falló (%s): %s", resp.status_code, resp.text)
    except Exception:
        logger.exception("Error al enviar WhatsApp ganador_vip a %s", celular)


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
        seen_slugs: set[str] = set()
        for item in data:
            slug = item.get("slug", "")
            if "5ta-" in slug:
                continue
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            raw_result = item.get("result", "")
            # Si el resultado trae 5 dígitos el último es la serie — lo descartamos
            resultado_limpio = raw_result[:-1] if len(raw_result) == 5 and raw_result.isdigit() else raw_result
            existing = (
                db.query(LoteriaResultado)
                .filter(LoteriaResultado.fecha == hoy_col, LoteriaResultado.slug == slug)
                .first()
            )
            if existing:
                existing.resultado = resultado_limpio
                existing.fetched_at = datetime.now(timezone.utc)
                resultados_map[slug] = existing
            else:
                nuevo = LoteriaResultado(
                    id=uuid.uuid4(),
                    fecha=hoy_col,
                    loteria=item.get("lottery", slug),
                    slug=slug,
                    resultado=resultado_limpio,
                    serie=item.get("series", ""),
                    fetched_at=datetime.now(timezone.utc),
                )
                db.add(nuevo)
                resultados_map[slug] = nuevo

        db.flush()

        # ── 3. Cruce con numbers_historic ─────────────────────────────────────
        # Se evalúan todos los números cuya vigencia (valid_until) cubra hoy,
        # no sólo los asignados hoy.
        historicos = (
            db.query(NumberHistoric)
            .join(
                NumberUser,
                (NumberUser.id_user == NumberHistoric.id_user)
                & (NumberUser.number == NumberHistoric.number)
                & (NumberUser.date_assigned == NumberHistoric.date),
            )
            .filter(
                NumberUser.date_assigned <= hoy_col,
                NumberUser.valid_until >= hoy_col,
            )
            .all()
        )

        nuevos_aciertos = 0
        _notificados_esta_corrida: set = set()
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

                        # ── Notificar ganador ────────────────────────────────
                        cliente_h = db.query(Cliente).filter(Cliente.id == h.id_user).first()
                        if (
                            cliente_h
                            and cliente_h.enabled
                            and cliente_h.id not in _notificados_esta_corrida
                        ):
                            _notificados_esta_corrida.add(cliente_h.id)
                            tipo_legible = {
                                "exacto": "Exacto",
                                "directo_devuelto": "Directo Devuelto",
                                "tres_orden": "Tres en Orden",
                                "tres_desorden": "Tres en Desorden",
                            }.get(tipo, tipo)
                            if cliente_h.vip:
                                _notificar_ganador_vip(
                                    celular=cliente_h.celular,
                                    numero=h.number,
                                    loteria=resultado.loteria,
                                    resultado_num=resultado.resultado,
                                    tipo=tipo_legible,
                                )
                                logger.info(
                                    "Ganador VIP notificado: %s (%s) — %s %s %s",
                                    cliente_h.nombre, cliente_h.celular,
                                    resultado.loteria, resultado.resultado, tipo,
                                )
                            else:
                                _notificar_ganador_free(
                                    celular=cliente_h.celular,
                                    numero=h.number,
                                    loteria=resultado.loteria,
                                    resultado_num=resultado.resultado,
                                    tipo=tipo_legible,
                                )
                                cliente_h.enabled = False
                                logger.info(
                                    "Ganador free deshabilitado: %s (%s) — %s %s %s",
                                    cliente_h.nombre, cliente_h.celular,
                                    resultado.loteria, resultado.resultado, tipo,
                                )

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


def _reasignar_numeros_vencidos() -> None:
    """
    Recorre todos los clientes habilitados y reasigna números vencidos:
    - Número free: a todos (si no tiene o venció).
    - Número vip: solo a clientes vip (si no tiene o venció).
    """
    from sqlalchemy import select as _select

    db = SessionLocal()
    try:
        today = date.today()
        clientes = db.query(Cliente).filter(Cliente.enabled == True).all()
        asignados = 0
        print(f"   Procesando {len(clientes)} cliente(s)...")

        for c in clientes:
            # ── Número free ───────────────────────────────────────
            free_row = db.execute(
                _select(NumberUser).where(
                    NumberUser.id_user == c.id,
                    NumberUser.type == "free",
                )
            ).scalar_one_or_none()

            if free_row is None or free_row.valid_until < today:
                assign_number(db, c.id, "free", VIGENCIA_FREE)
                asignados += 1

            # ── Número vip (solo si el cliente es VIP) ────────────
            if c.vip:
                vip_row = db.execute(
                    _select(NumberUser).where(
                        NumberUser.id_user == c.id,
                        NumberUser.type == "vip",
                    )
                ).scalar_one_or_none()

                if vip_row is None or vip_row.valid_until < today:
                    nueva = assign_number(db, c.id, "vip", VIGENCIA_VIP)
                    asignados += 1
                    if c.celular:
                        _notificar_nuevo_numero_vip(c.celular, nueva.number, nueva.valid_until)

        db.commit()
        print(f"   Asignaciones realizadas: {asignados}")
        logger.info("Cron reasignacion numeros: %d asignaciones realizadas sobre %d clientes", asignados, len(clientes))
    except Exception:
        db.rollback()
        logger.exception("Error en cron _reasignar_numeros_vencidos")
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
    # Reasignación de números vencidos — cron UTC completo desde settings
    minuto, hora, dom, mes, dow = settings.CRON_NUMEROS.split()
    _scheduler.add_job(
        _reasignar_numeros_vencidos,
        trigger=CronTrigger(minute=minuto, hour=hora, day=dom, month=mes, day_of_week=dow, timezone="UTC"),
        id="reasignar_numeros",
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
    logger.info(
        "Scheduler iniciado — vip_check 03:00 UTC + reasignar_numeros '%s' UTC + loterias 4x/día",
        settings.CRON_NUMEROS,
    )


def stop() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido")
