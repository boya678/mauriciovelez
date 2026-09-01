import base64
import hashlib
import json
import logging
import re
import unicodedata
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
import psycopg2
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from psycopg2 import sql
from psycopg2.extras import execute_batch
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.database import SessionLocal, _SessionChat
from app.models.cliente import Cliente
from app.models.comprobante_vip import ComprobanteVip
from app.models.contacto import Contacto
from app.models.cuenta_vip import acumular_cuenta_vip
from app.models.loteria_resultado import LoteriaResultado
from app.models.mensajes_ia_procesado import MensajeIaProcesado
from app.models.numero_acierto import NumeroAcierto
from app.models.numbers_historic import NumberHistoric
from app.models.numbers_users import NumberUser
from app.models.suscripcion import Suscripcion
from app.models.transaccion_procesada import TransaccionProcesada
from app.services.notification_queue import push
from app.services.numbers import (
    assign_number,
    notificar_codigo_asignado,
    notificar_nuevo_numero_free,
    notificar_nuevo_numero_vip,
)
from app.services.chat_phone_resolver import resolve_real_phone_from_identifier
from app.services.servicios_config import (
    get_conferencia_config,
    get_conferencia_vip_config,
    get_numero_relampago_config,
)
from app.services.suscripciones import renovar_cliente
from app.services.vision_ia import analizar_imagen_con_ia
from app.core.live_events import publish_event

COLOMBIA_TZ = ZoneInfo("America/Bogota")
LOTERIAS_API = "https://portal.supergirosnortedelvalle.com/api/resultados"

logger = logging.getLogger(__name__)

CONTACT_TAG_KEYS = {"vip", "tipo_cliente", "estado", "nombre", "codigo_vip"}


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


def _phone_key(value: str | None) -> str:
    if not value:
        return ""
    digits = re.sub(r"\D", "", value)
    return digits[-10:] if len(digits) >= 10 else digits


def _sanitize_tag_value(value: str | None) -> str:
    if value is None:
        return ""
    sanitized = str(value).replace(",", " ").strip()
    return re.sub(r"\s+", " ", sanitized)


def _merge_contact_tags(
    existing_tags: str | None,
    vip: str,
    tipo_cliente: str,
    estado: str,
    nombre: str,
    codigo_vip: str,
) -> str:
    tags = existing_tags or ""
    parsed: list[tuple[str | None, str]] = []
    for part in tags.split(","):
        token = part.strip()
        if not token:
            continue
        if ":" in token:
            key, value = token.split(":", 1)
            parsed.append((key.strip().lower(), f"{key.strip()}:{value.strip()}"))
        else:
            parsed.append((None, token))

    kept = [raw for key, raw in parsed if key not in CONTACT_TAG_KEYS]
    kept.extend([
        f"vip:{vip}",
        f"tipo_cliente:{tipo_cliente}",
        f"estado:{estado}",
        f"nombre:{nombre}",
        f"codigo_vip:{codigo_vip}",
    ])
    return ",".join(kept)

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


def _sincronizar_tags_contactos() -> None:
    """
    Sincroniza en DB2 (tabla contactos.tags) el estado de cada número con datos de DB1:
    - vip: si/no
    - tipo_cliente: entero
    - estado: activo/inactivo/no_cliente
    - nombre: nombre del cliente
    - codigo_vip: código del cliente
    """
    print("[CRON contactos] Inicio")
    if not settings.DATABASE_URL_2:
        logger.warning("CRON_CONTACTOS omitido: DATABASE_URL_2 no está configurada")
        return

    db = SessionLocal()
    conn2 = None
    try:
        clientes_rows = (
            db.query(
                Cliente.celular,
                Cliente.vip,
                Cliente.tipo_cliente,
                Cliente.enabled,
                Cliente.nombre,
                Cliente.codigo_vip,
            )
            .all()
        )

        clientes_by_phone: dict[str, tuple[str, str, str, str, str]] = {}
        for celular, vip, tipo_cliente, enabled, nombre, codigo_vip in clientes_rows:
            k = _phone_key(celular)
            if not k:
                continue
            vip_tag = "si" if bool(vip) else "no"
            tipo_tag = str(tipo_cliente if tipo_cliente is not None else "")
            estado_tag = "activo" if bool(enabled) else "inactivo"
            nombre_tag = _sanitize_tag_value(nombre)
            codigo_vip_tag = _sanitize_tag_value(codigo_vip)
            clientes_by_phone[k] = (vip_tag, tipo_tag, estado_tag, nombre_tag, codigo_vip_tag)

        conn2 = psycopg2.connect(settings.DATABASE_URL_2)
        conn2.autocommit = False

        with conn2.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT id, tags FROM {}.contactos").format(
                    sql.Identifier(settings.DATABASE_SCHEMA_2)
                )
            )
            contactos = cur.fetchall()

            updates: list[tuple[str, str]] = []
            activos = inactivos = no_cliente = 0
            for contacto_id, tags in contactos:
                k = _phone_key(contacto_id)
                if k in clientes_by_phone:
                    vip_tag, tipo_tag, estado_tag, nombre_tag, codigo_vip_tag = clientes_by_phone[k]
                else:
                    vip_tag, tipo_tag, estado_tag, nombre_tag, codigo_vip_tag = "no", "", "no_cliente", "", ""

                if estado_tag == "activo":
                    activos += 1
                elif estado_tag == "inactivo":
                    inactivos += 1
                else:
                    no_cliente += 1

                new_tags = _merge_contact_tags(tags, vip_tag, tipo_tag, estado_tag, nombre_tag, codigo_vip_tag)
                if (tags or "") != new_tags:
                    updates.append((new_tags, contacto_id))

            if updates:
                update_sql = sql.SQL("UPDATE {}.contactos SET tags = %s WHERE id = %s").format(
                    sql.Identifier(settings.DATABASE_SCHEMA_2)
                ).as_string(conn2)
                execute_batch(cur, update_sql, updates, page_size=1000)

        conn2.commit()
        print(
            f"[CRON contactos] Fin — contactos={len(contactos)} actualizados={len(updates)} "
            f"activos={activos} inactivos={inactivos} no_cliente={no_cliente}"
        )
        logger.info(
            "Cron contactos: %d contactos, %d actualizados (activos=%d inactivos=%d no_cliente=%d)",
            len(contactos),
            len(updates),
            activos,
            inactivos,
            no_cliente,
        )
    except Exception:
        if conn2 is not None:
            conn2.rollback()
        print("[CRON contactos] ERROR")
        logger.exception("Error en cron _sincronizar_tags_contactos")
    finally:
        if conn2 is not None:
            conn2.close()
        db.close()


# ── Procesamiento automático de pagos via IA ─────────────────────────────────

def _strip_cc(phone: str) -> str:
    """Quita el código de país y devuelve los 10 dígitos locales colombianos."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 12 and digits.startswith("57"):
        return digits[2:]
    if len(digits) > 10:
        return digits[-10:]
    return digits


def _is_valid_local_phone(phone: str | None) -> bool:
    return bool(phone and re.fullmatch(r"\d{10}", phone))


def _analizar_imagen_con_ia(base64_img: str, mime_type: str) -> dict:
    """Wrapper local — delega al servicio compartido."""
    return analizar_imagen_con_ia(base64_img, mime_type)


def _crear_cliente_vip(db, celular_local: str, celular_wp: str) -> Cliente:
    """Crea un cliente nuevo tipo VIP (tipo_cliente=1, vip=True) y dispara
    todas las notificaciones, igual que el endpoint admin/clientes POST."""
    _seq = db.execute(text("SELECT nextval('seq_vip_codigo')")).scalar()
    codigo_vip = f"{_seq:05d}"

    nuevo = Cliente(
        id=uuid.uuid4(),
        nombre=celular_local,          # nombre temporal = celular hasta que lo complete
        celular=celular_local,
        codigo_pais="57",
        vip=True,
        enabled=True,
        tipo_cliente=1,
        codigo_vip=codigo_vip,
        saldo=0,
    )
    db.add(nuevo)
    db.flush()

    free = assign_number(db, nuevo.id, "free")
    from dateutil.relativedelta import relativedelta
    now = datetime.now(timezone.utc)
    db.add(Suscripcion(
        cliente_id=nuevo.id,
        inicio=now,
        fin=now + relativedelta(months=1),
        activa=True,
    ))
    acumular_cuenta_vip(db)
    vip_num = assign_number(db, nuevo.id, "vip")
    db.flush()
    db.commit()

    notificar_nuevo_numero_free(celular_wp, free.number, free.valid_until)
    notificar_nuevo_numero_vip(celular_wp, vip_num.number, vip_num.valid_until)
    notificar_codigo_asignado(celular_wp, 1, codigo_vip)
    publish_event("nuevo_cliente", {"nombre": nuevo.nombre})
    return nuevo


def _marcar_mensaje_procesada(db, msg_id: uuid.UUID) -> None:
    """Oculta el mensaje del listado admin (igual que _marcar_procesada en admin_transacciones)."""
    existente = db.execute(
        select(TransaccionProcesada).where(TransaccionProcesada.id_externo == msg_id)
    ).scalar_one_or_none()
    if existente is None:
        db.add(TransaccionProcesada(id_externo=msg_id, estado=False))
    else:
        existente.estado = False
    db.commit()


def _procesar_pagos_automatico() -> None:
    """
    Cada CRON_PAGOS:
    1. Consulta imágenes de hoy en chat DB no analizadas aún por la IA.
    2. Llama a Azure OpenAI Vision para cada una.
    3. Si es comprobante con monto == VIP_AMOUNT:
       - Intenta insertar en comprobantes_vip (UNIQUE en comprobante_num).
       - Si inserta OK  → renueva o crea cliente VIP y oculta el mensaje.
       - Si duplicado   → solo oculta el mensaje, no renueva.
    4. Si ocurre cualquier error → print en consola, NO se marca nada.
    """
    if not settings.AZURE_OPENAI_ENDPOINT or not settings.AZURE_OPENAI_API_KEY:
        print("[CRON pagos] Azure OpenAI no configurado, saltando.")
        return
    if _SessionChat is None:
        print("[CRON pagos] Chat DB no configurada, saltando.")
        return

    hoy = datetime.now(COLOMBIA_TZ).date()
    schema = settings.DATABASE_SCHEMA_2
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', schema):
        print(f"[CRON pagos] Schema inválido: {schema}")
        return

    print(f"[CRON pagos] Inicio — {hoy}")

    db = SessionLocal()
    chat_db = _SessionChat()
    try:
        # ── 1. Mensajes con imagen de hoy ───────────────────────────────────
        rows = chat_db.execute(text(f"""
            SELECT
                m.id,
                m.media_content,
                m.media_mime_type,
                c.phone
            FROM {schema}.messages m
            JOIN {schema}.conversations c ON c.id = m.conversation_id
            WHERE m.message_type = 'image'
              AND (m.created_at AT TIME ZONE 'America/Bogota')::date = :fecha
              AND m.media_content IS NOT NULL
            ORDER BY m.created_at ASC
        """), {"fecha": hoy}).mappings().all()

        # ── 2. Filtrar los ya analizados (solo contra los IDs de hoy) ─────────
        today_ids = [r["id"] for r in rows]
        ya_procesados: set[uuid.UUID] = set()
        if today_ids:
            ya_procesados = set(
                db.execute(
                    select(MensajeIaProcesado.message_id).where(
                        MensajeIaProcesado.message_id.in_(today_ids)
                    )
                ).scalars().all()
            )

        pendientes = [r for r in rows if r["id"] not in ya_procesados]
        conferencia_cfg = get_conferencia_config(db)
        conferencia_vip_cfg = get_conferencia_vip_config(db)
        relampago_cfg = get_numero_relampago_config(db)
        print(f"[CRON pagos] {len(pendientes)} imágenes pendientes de análisis")

        for row in pendientes:
            msg_id: uuid.UUID = row["id"]
            base64_img: str = row["media_content"]
            mime_type: str = row["media_mime_type"] or "image/jpeg"
            phone_orig: str = row["phone"] or ""
            phone_resuelto = resolve_real_phone_from_identifier(chat_db, schema, phone_orig) or phone_orig
            celular_local = _strip_cc(phone_resuelto)
            celular_wp = re.sub(r"\D", "", phone_resuelto) or f"57{celular_local}"

            # ── Hash SHA-256 de la imagen (bytes reales, no el string base64) ──
            try:
                image_bytes = base64.b64decode(base64_img)
                image_hash = hashlib.sha256(image_bytes).hexdigest()
            except Exception as exc:
                print(f"[CRON pagos] ERROR calculando hash msg={msg_id}: {exc}")
                continue

            # ── Chequeo extra: ¿ya procesamos esta imagen física antes? ─────────
            hash_ya_procesado = db.execute(
                select(MensajeIaProcesado).where(MensajeIaProcesado.image_hash == image_hash)
            ).scalars().first()

            if hash_ya_procesado:
                # Misma imagen, distinto message_id — registrar sin llamar a la IA
                print(f"[CRON pagos] msg={msg_id}: imagen ya procesada (hash={image_hash[:8]}...) — marcando sin IA")
                try:
                    db.add(MensajeIaProcesado(
                        message_id=msg_id,
                        es_comprobante=hash_ya_procesado.es_comprobante,
                        monto_extraido=hash_ya_procesado.monto_extraido,
                        comprobante_num=hash_ya_procesado.comprobante_num,
                        numero_destino=hash_ya_procesado.numero_destino,
                        nombre_destino=hash_ya_procesado.nombre_destino,
                        destino_valido=hash_ya_procesado.destino_valido,
                        image_hash=image_hash,
                    ))
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    print(f"[CRON pagos] ERROR marcando duplicado hash msg={msg_id}: {exc}")
                # Ocultar el mensaje también
                try:
                    _marcar_mensaje_procesada(db, msg_id)
                except Exception as exc:
                    print(f"[CRON pagos] ERROR ocultando mensaje hash-dup msg={msg_id}: {exc}")
                continue

            # ── 3. Llamada a la IA ─────────────────────────────────────────────
            try:
                resultado_ia = _analizar_imagen_con_ia(base64_img, mime_type)
            except Exception as exc:
                print(f"[CRON pagos] ERROR IA msg={msg_id}: {exc}")
                continue  # no marcamos nada, se reintentará

            es_comprobante: bool = bool(resultado_ia.get("es_comprobante"))
            comprobante_num = resultado_ia.get("comprobante_num") or None
            monto_raw = resultado_ia.get("monto")
            monto = Decimal(str(monto_raw)) if monto_raw is not None else None
            numero_destino = resultado_ia.get("numero_destino") or None
            nombre_destino = resultado_ia.get("nombre_destino") or None
            destino_valido = bool(resultado_ia.get("destino_valido"))

            # ── 4. Registrar que ya se analizó (independiente del resultado) ───
            try:
                db.add(MensajeIaProcesado(
                    message_id=msg_id,
                    es_comprobante=es_comprobante,
                    monto_extraido=monto,
                    comprobante_num=comprobante_num,
                    numero_destino=numero_destino,
                    nombre_destino=nombre_destino,
                    destino_valido=destino_valido,
                    image_hash=image_hash,
                ))
                db.commit()
            except Exception as exc:
                db.rollback()
                print(f"[CRON pagos] ERROR guardando MensajeIaProcesado msg={msg_id}: {exc}")
                continue

            # ── 5. ¿Aplica para renovación? ────────────────────────────────────
            if not es_comprobante:
                print(f"[CRON pagos] msg={msg_id}: no es comprobante, ignorado")
                continue

            if not comprobante_num:
                print(f"[CRON pagos] msg={msg_id}: comprobante sin número extraído, ignorado")
                continue

            if not destino_valido:
                print(
                    f"[CRON pagos] msg={msg_id}: destino no validado "
                    f"(numero='{numero_destino}', nombre='{nombre_destino}'), queda para validación manual"
                )
                continue

            if not _is_valid_local_phone(celular_local):
                print(
                    f"[CRON pagos] msg={msg_id}: identificador sin celular resoluble "
                    f"(raw='{phone_orig}', resolved='{phone_resuelto}'), ignorado"
                )
                continue

            cliente_actual = db.execute(
                select(Cliente).where(Cliente.celular == celular_local)
            ).scalar_one_or_none()
            es_vip_activo = bool(cliente_actual and cliente_actual.vip and cliente_actual.enabled)

            is_conferencia_vip = bool(
                conferencia_vip_cfg.activo
                and conferencia_vip_cfg.valor > 0
                and conferencia_vip_cfg.fecha_aviso
                and conferencia_vip_cfg.link_youtube
                and monto is not None
                and int(monto) == conferencia_vip_cfg.valor
                and es_vip_activo
            )
            is_relampago = bool(
                relampago_cfg.activo
                and relampago_cfg.valor > 0
                and monto is not None
                and int(monto) == relampago_cfg.valor
            )
            is_conferencia = bool(
                conferencia_cfg.activo
                and conferencia_cfg.valor > 0
                and conferencia_cfg.fecha_aviso
                and conferencia_cfg.link_youtube
                and monto is not None
                and int(monto) == conferencia_cfg.valor
            )

            if not is_conferencia_vip and not is_conferencia and not is_relampago and (monto is None or int(monto) != settings.VIP_AMOUNT):
                print(
                    f"[CRON pagos] msg={msg_id}: monto {monto} no coincide con VIP ({settings.VIP_AMOUNT}) "
                    f"ni relampago ({relampago_cfg.valor if relampago_cfg.activo else 'inactivo'}) "
                    f"ni conferencia ({conferencia_cfg.valor if conferencia_cfg.activo else 'inactivo'}) "
                    f"ni conferencia_vip ({conferencia_vip_cfg.valor if conferencia_vip_cfg.activo else 'inactivo'}), ignorado"
                )
                continue

            # ── 6. Intentar registrar comprobante único ─────────────────────────
            comprobante_nuevo = False
            try:
                db.add(ComprobanteVip(
                    comprobante_num=comprobante_num,
                    celular=celular_local,
                    monto=monto,
                    descripcion=(
                        "conferencia_vip" if is_conferencia_vip
                        else "conferencia" if is_conferencia
                        else "numero_relampago" if is_relampago
                        else "pago vip"
                    ),
                    message_id=msg_id,
                    image_hash=image_hash,
                ))
                db.commit()
                comprobante_nuevo = True
            except IntegrityError:
                db.rollback()
                print(f"[CRON pagos] msg={msg_id} celular={celular_local}: comprobante '{comprobante_num}' ya procesado antes — solo se oculta")
            except Exception as exc:
                db.rollback()
                print(f"[CRON pagos] ERROR insertando ComprobanteVip msg={msg_id}: {exc}")
                continue

            # ── 7. Ocultar mensaje del admin ───────────────────────────────────
            try:
                _marcar_mensaje_procesada(db, msg_id)
            except Exception as exc:
                print(f"[CRON pagos] ERROR ocultando mensaje msg={msg_id}: {exc}")
                continue

            if not comprobante_nuevo:
                continue  # duplicado: ya ocultamos, no renovamos

            if is_conferencia_vip:
                if settings.WHATSAPP_NOTIFICAR_CONFERENCIA:
                    try:
                        push(
                            "notificar_conferencia",
                            celular_wp,
                            {
                                "fecha_aviso": conferencia_vip_cfg.fecha_aviso,
                                "link_youtube": conferencia_vip_cfg.link_youtube,
                            },
                        )
                    except Exception as exc:
                        print(f"[CRON pagos] ERROR notificando conferencia_vip msg={msg_id}: {exc}")
                print(
                    f"[CRON pagos] msg={msg_id}: registrado como conferencia_vip "
                    f"(monto={monto}, link={conferencia_vip_cfg.link_youtube})"
                )
                continue

            if is_conferencia:
                if settings.WHATSAPP_NOTIFICAR_CONFERENCIA:
                    try:
                        push(
                            "notificar_conferencia",
                            celular_wp,
                            {
                                "fecha_aviso": conferencia_cfg.fecha_aviso,
                                "link_youtube": conferencia_cfg.link_youtube,
                            },
                        )
                    except Exception as exc:
                        print(f"[CRON pagos] ERROR notificando conferencia msg={msg_id}: {exc}")
                print(
                    f"[CRON pagos] msg={msg_id}: registrado como conferencia "
                    f"(monto={monto}, link={conferencia_cfg.link_youtube})"
                )
                continue

            if is_relampago:
                if relampago_cfg.numero and settings.WHATSAPP_NOTIFICAR_RELAMPAGO:
                    try:
                        push(
                            "notificar_relampago",
                            celular_wp,
                            {"texto": relampago_cfg.numero},
                        )
                    except Exception as exc:
                        print(f"[CRON pagos] ERROR notificando relampago msg={msg_id}: {exc}")
                print(
                    f"[CRON pagos] msg={msg_id}: registrado como numero_relampago "
                    f"(monto={monto}, numero={relampago_cfg.numero or 'sin_numero'}, celular={celular_wp})"
                )
                continue

            # ── 8. Renovar o crear cliente ─────────────────────────────────────
            try:
                cliente = db.execute(
                    select(Cliente).where(Cliente.celular == celular_local)
                ).scalar_one_or_none()

                if cliente:
                    if cliente.tipo_cliente != 1:
                        print(f"[CRON pagos] msg={msg_id}: cliente {celular_local} tipo {cliente.tipo_cliente}, no se renueva")
                        continue
                    nueva_sus, era_vip = renovar_cliente(
                        db=db,
                        cliente=cliente,
                        platform_user_id=None,  # proceso automático
                        usuario="sistema_pagos",
                        audit_action="RENOVAR_PAGO_AUTO",
                        audit_entity="comprobantes_vip",
                        audit_entity_id=str(msg_id),
                    )
                    db.commit()
                    if not era_vip:
                        publish_event("nuevo_vip", {"nombre": cliente.nombre})
                    print(f"[CRON pagos] msg={msg_id}: renovado cliente {celular_local} hasta {nueva_sus.fin.date()}")
                else:
                    nuevo_cli = _crear_cliente_vip(db, celular_local, celular_wp)
                    print(f"[CRON pagos] msg={msg_id}: cliente nuevo VIP creado {celular_local} id={nuevo_cli.id}")

            except Exception as exc:
                db.rollback()
                print(f"[CRON pagos] ERROR en renovación/creación msg={msg_id} celular={celular_local}: {exc}")
                continue

    except Exception as exc:
        print(f"[CRON pagos] ERROR general: {exc}")
        logger.exception("Error en _procesar_pagos_automatico")
    finally:
        chat_db.close()
        db.close()
        print(f"[CRON pagos] Fin — {hoy}")


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
    _scheduler.add_job(
        _sincronizar_tags_contactos,
        trigger=_parse_cron(settings.CRON_CONTACTOS),
        id="contactos_tags",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        _procesar_pagos_automatico,
        trigger=_parse_cron(settings.CRON_PAGOS),
        id="pagos_automatico",
        replace_existing=True,
        misfire_grace_time=600,
    )
    _scheduler.start()
    logger.info(
        "Scheduler iniciado (hora Colombia) — vip_check '%s' | numeros '%s' | loterias '%s' | contactos '%s' | pagos '%s'",
        settings.CRON_VIP_CHECK,
        settings.CRON_NUMEROS,
        settings.CRON_LOTERIAS,
        settings.CRON_CONTACTOS,
        settings.CRON_PAGOS,
    )


def stop() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido")
