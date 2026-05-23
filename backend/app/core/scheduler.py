import logging
import unicodedata
import uuid
from datetime import date, datetime, timezone

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.database import SessionLocal
from app.models.cliente import Cliente
from app.models.contacto import Contacto
from app.models.loteria_resultado import LoteriaResultado
from app.models.numero_acierto import NumeroAcierto
from app.models.numbers_historic import NumberHistoric
from app.models.numbers_users import NumberUser
from app.models.suscripcion import Suscripcion
from app.services.numbers import assign_number, notificar_nuevo_numero_free, notificar_nuevo_numero_vip
from app.services.notification_queue import push
from app.core.live_events import publish_event

COLOMBIA_TZ = ZoneInfo("America/Bogota")
LOTERIAS_API = "https://portal.supergirosnortedelvalle.com/api/resultados"

logger = logging.getLogger(__name__)


def _normalizar(texto: str) -> str:
    """Convierte a mayúsculas y elimina tildes/diacríticos."""
    nfkd = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sin_tildes.upper()


def _loterias_evitar() -> set[str]:
    """Devuelve el conjunto de nombres normalizados a evitar."""
    raw = settings.LOTERIAS_EVITAR
    if not raw:
        return set()
    return {_normalizar(n.strip()) for n in raw.split(",") if n.strip()}

_scheduler = BackgroundScheduler(timezone="UTC")


def _clasificar(numero: str, resultado: str) -> list[str]:
    """
    Devuelve los tipos de acierto (máximo uno, el de mayor jerarquía):
    - directo:        los 4 dígitos coinciden exactamente
    - directo_metodo: primer dígito igual + últimos 3 en orden inverso (3267 vs 3762)
    - tres_directo:   últimos 3 dígitos iguales en orden (sin importar el primero)
    - tres_metodo:    últimos 3 dígitos en orden inverso (sin importar el primero)
    """
    n4 = numero.zfill(4)[-4:]
    r4 = resultado.zfill(4)[-4:]
    n3 = n4[-3:]
    r3 = r4[-3:]
    r3_rev = r3[::-1]

    if n4 == r4:
        return ["directo"]
    if n4[0] == r4[0] and n3 == r3_rev:
        return ["directo_metodo"]
    if n3 == r3:
        return ["tres_directo"]
    if n3 == r3_rev:
        return ["tres_metodo"]
    return []


def _notificar_ganador_free(celular: str, numero: str, loteria: str, resultado_num: str) -> None:
    push("ganador_free", celular, {"numero": numero, "loteria": loteria, "resultado_num": resultado_num})


def _notificar_ganador_vip(celular: str, numero: str, loteria: str, resultado_num: str) -> None:
    push("ganador_vip", celular, {"numero": numero, "loteria": loteria, "resultado_num": resultado_num})


def _procesar_loterias(fecha: date | None = None) -> None:
    """
    1. Obtiene resultados de la API externa para `fecha` (hoy en Colombia si None).
    2. Hace upsert en loteria_resultados.
    3. Cruza con numbers_historic del mismo día y registra en numero_aciertos.
    """
    hoy_col = fecha or datetime.now(COLOMBIA_TZ).date()
    fecha_str = hoy_col.strftime("%Y-%m-%d")
    print(f"[CRON loterias] Inicio — {fecha_str}")
    logger.info("Procesando loterias para %s", fecha_str)

    db = SessionLocal()
    try:
        # ── 1. Fetch API externa ──────────────────────────────────────────────
        try:
            fecha_param = hoy_col.strftime("%d/%m/%Y")
            resp = httpx.get(LOTERIAS_API, params={"fecha": fecha_param}, timeout=15)
            resp.raise_for_status()
            data = resp.json().get("resultados", [])
        except Exception:
            logger.exception("Error al consultar API loterias para %s", fecha_str)
            return

        if not data:
            logger.info("Sin resultados de loterias para %s", fecha_str)
            return

        # ── 2. Upsert resultados ──────────────────────────────────────────────
        resultados_map: dict[str, LoteriaResultado] = {}
        seen_slugs: set[str] = set()
        evitar = _loterias_evitar()
        for item in data:
            lottery = item.get("lottery", {})
            slug = lottery.get("name", "")
            if not slug:
                continue
            if slug in seen_slugs:
                continue
            display_name = lottery.get("display_name", slug)
            if evitar and _normalizar(display_name) in evitar:
                logger.debug("Loteria ignorada por LOTERIAS_EVITAR: %s", display_name)
                continue
            seen_slugs.add(slug)
            raw_result = item.get("number", "")
            # La nueva API ya devuelve 4 dígitos directamente
            resultado_limpio = raw_result.zfill(4) if raw_result.isdigit() else raw_result
            serie_raw = item.get("zodiac_sign") or ""
            # zodiac_sign puede ser "serie: 179" o un signo zodiacal — guardamos tal cual
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
                    loteria=display_name,
                    slug=slug,
                    resultado=resultado_limpio,
                    serie=serie_raw,
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
                        if cliente_h and cliente_h.enabled:
                            celular_wp = f"{cliente_h.codigo_pais or '57'}{cliente_h.celular}" if cliente_h.celular else None
                            # ── Publicar evento live ────────────────────────
                            veces_gano = db.query(NumeroAcierto).join(
                                NumberHistoric, NumeroAcierto.historic_id == NumberHistoric.id,
                            ).filter(NumberHistoric.id_user == h.id_user).count()
                            publish_event("ganador", {
                                "nombre": cliente_h.nombre,
                                "numero": h.number,
                                "loteria": resultado.loteria,
                                "tipo_acierto": tipo,
                                "veces_gano": veces_gano,
                            })
                            tipo_legible = {
                                "directo": "Directo",
                                "directo_metodo": "Directo Método",
                                "tres_directo": "Tres Directo",
                                "tres_metodo": "Tres Método",
                            }.get(tipo, tipo)
                            if cliente_h.vip:
                                if celular_wp:
                                    _notificar_ganador_vip(
                                        celular=celular_wp,
                                        numero=h.number,
                                        loteria=resultado.loteria,
                                        resultado_num=resultado.resultado,
                                    )
                                logger.info(
                                    "Ganador VIP notificado: %s (%s) — %s %s %s",
                                    cliente_h.nombre, cliente_h.celular,
                                    resultado.loteria, resultado.resultado, tipo,
                                )
                            else:
                                if celular_wp:
                                    _notificar_ganador_free(
                                        celular=celular_wp,
                                        numero=h.number,
                                        loteria=resultado.loteria,
                                        resultado_num=resultado.resultado,
                                    )
                                cliente_h.enabled = False
                                db.add(Contacto(
                                    id=uuid.uuid4(),
                                    cliente_id=cliente_h.id,
                                    numero=h.number,
                                    loteria=resultado.loteria,
                                    tipo_acierto=tipo_legible,
                                ))
                                logger.info(
                                    "Ganador free deshabilitado: %s (%s) — %s %s %s",
                                    cliente_h.nombre, cliente_h.celular,
                                    resultado.loteria, resultado.resultado, tipo,
                                )

        db.commit()
        print(f"[CRON loterias] Fin — {fecha_str}: {len(data)} resultados, {nuevos_aciertos} nuevos aciertos")
        logger.info(
            "Loterias %s: %d resultados, %d historicos, %d nuevos aciertos",
            fecha_str, len(data), len(historicos), nuevos_aciertos,
        )
    except Exception:
        db.rollback()
        print(f"[CRON loterias] ERROR — {fecha_str}")
        logger.exception("Error en _procesar_loterias para %s", fecha_str)
    finally:
        db.close()


def _enviar_recordatorio_vencimiento(celular: str, nombre: str) -> None:
    push("recordatorio_vencimiento", celular, {})


def _desactivar_vip_vencidos() -> None:
    """
    1. Envía recordatorio a clientes VIP cuya suscripción vence en exactamente 3 días.
    2. Marca como vip=False a todos los clientes cuya suscripción activa
       haya vencido y que no tengan otra suscripción vigente.
    También marca activa=False las suscripciones vencidas.
    """
    print("[CRON vip_check] Inicio")
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # 0. Recordatorio: suscripciones activas que vencen en 3 días (+/- 1h de margen)
        from datetime import timedelta
        ventana_inicio = now + timedelta(days=3) - timedelta(hours=1)
        ventana_fin    = now + timedelta(days=3) + timedelta(hours=1)
        por_vencer = (
            db.query(Suscripcion)
            .filter(
                Suscripcion.activa == True,
                Suscripcion.fin >= ventana_inicio,
                Suscripcion.fin <= ventana_fin,
            )
            .all()
        )
        recordatorios = 0
        for s in por_vencer:
            cliente = db.get(Cliente, s.cliente_id)
            if cliente and cliente.celular:
                celular_wp = f"{cliente.codigo_pais or '57'}{cliente.celular}"
                _enviar_recordatorio_vencimiento(celular_wp, cliente.nombre or "")
                recordatorios += 1
        print(f"[CRON vip_check] Recordatorios enviados: {recordatorios}")

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
            c.enabled = False
            logger.info("VIP desactivado y cuenta inhabilitada: %s (%s)", c.nombre, c.celular)

        db.commit()
        print(f"[CRON vip_check] Fin — {len(vencidas)} suscripciones vencidas, {len(expirados)} clientes desactivados")
        logger.info(
            "Cron vip_check: %d recordatorios, %d suscripciones vencidas, %d clientes desactivados",
            recordatorios, len(vencidas), len(expirados),
        )
    except Exception:
        db.rollback()
        print("[CRON vip_check] ERROR")
        logger.exception("Error en cron _desactivar_vip_vencidos")
    finally:
        db.close()


def _reasignar_numeros_vencidos() -> None:
    """
    Recorre todos los clientes habilitados y reasigna números vencidos:
    - Número free: a todos (si no tiene o venció).
    - Número vip: solo a clientes vip (si no tiene o venció).
    """
    print("[CRON numeros] Inicio")
    from sqlalchemy import select as _select

    db = SessionLocal()
    try:
        today = datetime.now(COLOMBIA_TZ).date()
        clientes = db.query(Cliente).filter(
            Cliente.enabled == True,
            Cliente.tipo_cliente == 1,
        ).all()
        asignados = 0
        print(f"[CRON numeros] Procesando {len(clientes)} cliente(s)...")

        for c in clientes:
            try:
                # ── Número free ───────────────────────────────────
                free_row = db.execute(
                    _select(NumberUser).where(
                        NumberUser.id_user == c.id,
                        NumberUser.type == "free",
                    )
                ).scalar_one_or_none()

                if free_row is None or free_row.valid_until < today:
                    nueva_free = assign_number(db, c.id, "free")
                    db.commit()  # Persistir ANTES de notificar para evitar inconsistencias
                    asignados += 1
                    if c.celular:
                        celular_wp = f"{c.codigo_pais or '57'}{c.celular}"
                        notificar_nuevo_numero_free(celular_wp, nueva_free.number, nueva_free.valid_until)

                # ── Número vip (solo si el cliente es VIP) ────────
                if c.vip:
                    vip_row = db.execute(
                        _select(NumberUser).where(
                            NumberUser.id_user == c.id,
                            NumberUser.type == "vip",
                        )
                    ).scalar_one_or_none()

                    if vip_row is None or vip_row.valid_until < today:
                        nueva = assign_number(db, c.id, "vip")
                        db.commit()  # Persistir ANTES de notificar para evitar inconsistencias
                        asignados += 1
                        if c.celular:
                            celular_wp = f"{c.codigo_pais or '57'}{c.celular}"
                            notificar_nuevo_numero_vip(celular_wp, nueva.number, nueva.valid_until)
            except Exception:
                db.rollback()
                logger.exception("Error procesando cliente %s (%s) en reasignación", c.id, c.celular)
                continue

        print(f"[CRON numeros] Fin — {asignados} asignaciones realizadas sobre {len(clientes)} clientes")
        logger.info("Cron reasignacion numeros: %d asignaciones realizadas sobre %d clientes", asignados, len(clientes))
    except Exception:
        db.rollback()
        print("[CRON numeros] ERROR")
        logger.exception("Error en cron _reasignar_numeros_vencidos")
    finally:
        db.close()


def _parse_cron(expr: str) -> CronTrigger:
    """Parsea una expresión cron de 5 campos y retorna un CronTrigger en hora Colombia."""
    minuto, hora, dom, mes, dow = expr.split()
    return CronTrigger(minute=minuto, hour=hora, day=dom, month=mes, day_of_week=dow, timezone="America/Bogota")


def start() -> None:
    """Registra los jobs y arranca el scheduler."""
    _scheduler.add_job(
        _desactivar_vip_vencidos,
        trigger=_parse_cron(settings.CRON_VIP_CHECK),
        id="vip_check",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        _reasignar_numeros_vencidos,
        trigger=_parse_cron(settings.CRON_NUMEROS),
        id="reasignar_numeros",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        _procesar_loterias,
        trigger=_parse_cron(settings.CRON_LOTERIAS),
        id="loterias",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info(
        "Scheduler iniciado (hora Colombia) — vip_check '%s' | numeros '%s' | loterias '%s'",
        settings.CRON_VIP_CHECK, settings.CRON_NUMEROS, settings.CRON_LOTERIAS,
    )


def stop() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido")
