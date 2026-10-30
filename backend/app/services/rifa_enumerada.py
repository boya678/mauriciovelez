"""Servicio 'Rifa enumerada': boletas con número (0000-9999 barajado) enviadas por WhatsApp."""
import base64
import hashlib
import logging
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import SessionLocal
from app.models.parametro import Parametro
from app.models.rifa_enumerada import RifaEnumeradaAviso, RifaEnumeradaBase, RifaEnumeradaBoleta, RifaEnumeradaLote, RifaEnumeradaNumero
from app.services.rifa_enumerada_util import render_boleta
from app.services.servicios_config import KEY_RE_SIGUIENTE

logger = logging.getLogger(__name__)

BASE_ID = 1
TOTAL_NUMEROS = 10000
MAX_MPS = 40               # tope duro de mensajes por segundo; no es configurable
ESPACIO_RONDAS_S = 6.5     # Meta: 1 mensaje cada 6 s al mismo celular
TRABAJADORES = 24
REINTENTOS_PAR = 2         # reintentos ante el error 131056 (límite por celular)


# ── Números barajados ─────────────────────────────────────────────────────────

def _rebarajar(db: Session) -> None:
    db.execute(text(
        "UPDATE rifa_enum_numeros t SET orden = r.rn "
        "FROM (SELECT numero, ROW_NUMBER() OVER (ORDER BY random()) - 1 AS rn FROM rifa_enum_numeros) r "
        "WHERE t.numero = r.numero"
    ))


def tomar_numeros(db: Session, cantidad: int) -> list[str]:
    """Entrega los siguientes números de la lista barajada; al agotarla vuelve a barajar.
    Bloquea el puntero hasta el commit del llamador."""
    puntero = db.execute(
        select(Parametro).where(Parametro.clave == KEY_RE_SIGUIENTE).with_for_update()
    ).scalar_one()
    indice = int(puntero.valor) % TOTAL_NUMEROS
    entregados: list[str] = []

    while len(entregados) < cantidad:
        tomar = min(cantidad - len(entregados), TOTAL_NUMEROS - indice)
        entregados.extend(
            db.execute(
                select(RifaEnumeradaNumero.numero)
                .where(RifaEnumeradaNumero.orden >= indice, RifaEnumeradaNumero.orden < indice + tomar)
                .order_by(RifaEnumeradaNumero.orden)
            ).scalars().all()
        )
        indice += tomar
        if indice >= TOTAL_NUMEROS:
            _rebarajar(db)
            indice = 0

    puntero.valor = str(indice)
    return entregados


# ── Blob Storage ──────────────────────────────────────────────────────────────

def _contenedor():
    from azure.storage.blob import BlobServiceClient

    servicio = BlobServiceClient.from_connection_string(settings.RIFA_BLOB_STORAGE_CONNECTION_STRING)
    return servicio.get_container_client(settings.RIFA_CONTAINER)


def _nombre_blob(version: int, numero: str) -> str:
    return f"boletas/v{version}/{numero}.jpg"


def _subir_imagen(contenedor, version: int, numero: str, base: bytes) -> str:
    from azure.storage.blob import ContentSettings

    blob = contenedor.get_blob_client(_nombre_blob(version, numero))
    blob.upload_blob(
        render_boleta(base, numero),
        overwrite=True,
        content_settings=ContentSettings(content_type="image/jpeg", cache_control="public, max-age=31536000"),
    )
    return blob.url


def version_base(base: RifaEnumeradaBase) -> int:
    return int(base.updated_at.timestamp())


def verificar_blob_publico(base: RifaEnumeradaBase) -> None:
    """Sube una boleta de prueba y la pide sin credenciales: Meta la descargará igual."""
    contenedor = _contenedor()
    url = _subir_imagen(contenedor, version_base(base), "0000", bytes(base.imagen_data))
    respuesta = httpx.get(url, timeout=20)
    if respuesta.status_code != 200 or not respuesta.headers.get("content-type", "").startswith("image/"):
        raise RuntimeError(
            f"El contenedor no permite lectura anónima (HTTP {respuesta.status_code}); Meta no podría descargar las imágenes"
        )


# ── Envío ─────────────────────────────────────────────────────────────────────

class _Limitador:
    """Reparte turnos separados 1/MAX_MPS segundos: nunca supera el tope, ni en ráfagas."""

    def __init__(self, por_segundo: int):
        self._intervalo = 1.0 / por_segundo
        self._lock = threading.Lock()
        self._siguiente = time.monotonic()

    def esperar(self) -> None:
        with self._lock:
            ahora = time.monotonic()
            turno = max(ahora, self._siguiente)
            self._siguiente = turno + self._intervalo
        espera = turno - ahora
        if espera > 0:
            time.sleep(espera)


# Un solo limitador para todo el servicio: el tope de 40 mensajes por segundo no se supera ni con envíos simultáneos.
_LIMITADOR = _Limitador(MAX_MPS)


def _contenido_aviso() -> dict:
    return {
        "type": "template",
        "template": {"name": settings.WHATSAPP_TEMPLATE_NOTIFICACION_RIFA_ENUMERADA, "language": {"code": "es_CO"}},
    }


def contenido_boleta(url_imagen: str, numero: str) -> dict:
    # Mensaje normal, no plantilla: solo es válido dentro de la ventana de 24 h que abre el botón.
    return {"type": "image", "image": {"link": url_imagen, "caption": f"Boleta {numero}"}}


def _enviar_mensaje(http: httpx.Client, limitador: _Limitador, celular: str, contenido: dict):
    """Retorna (ok, wamid, error)."""
    cuerpo = {"messaging_product": "whatsapp", "to": celular, **contenido}
    cabeceras = {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    url = f"https://graph.facebook.com/v25.0/{settings.WHATSAPP_PHONE_ID}/messages"

    for intento in range(REINTENTOS_PAR + 1):
        limitador.esperar()
        try:
            resp = http.post(url, json=cuerpo, headers=cabeceras, timeout=20)
        except httpx.HTTPError as exc:
            return False, None, f"red: {exc}"[:300]

        if resp.status_code < 400:
            try:
                return True, resp.json()["messages"][0]["id"], None
            except (KeyError, IndexError, ValueError):
                return True, None, None

        try:
            error = resp.json()["error"]
            codigo, mensaje = error.get("code"), error.get("message", "")
        except (KeyError, ValueError):
            codigo, mensaje = None, resp.text[:200]
        if codigo == 131056 and intento < REINTENTOS_PAR:
            time.sleep(ESPACIO_RONDAS_S)
            continue
        return False, None, f"{codigo}: {mensaje}"[:300]
    return False, None, "sin respuesta"


def _nombre_envio(celular: str, numero: str, boleta_id: int, retirada: bool = False) -> str:
    # El hash sale del id de la boleta: un mismo número reenviado al mismo celular no se pisa.
    corto = hashlib.sha1(str(boleta_id).encode()).hexdigest()[:6]
    return f"envios/{celular}/{numero}_{corto}{'_retirada' if retirada else ''}.jpg"


def _registrar_envio_en_blob(contenedor, boleta_id: int, celular: str, numero: str, url_origen: str) -> None:
    """Deja la boleta enviada en envios/{celular}/ para consultarla por número de WhatsApp."""
    try:
        contenedor.get_blob_client(_nombre_envio(celular, numero, boleta_id)).start_copy_from_url(url_origen)
    except Exception:
        logger.warning("No se pudo copiar la boleta %s de %s a envios/", numero, celular, exc_info=True)


def _procesar_aviso(aviso_id: int, http: httpx.Client) -> None:
    db = SessionLocal()
    try:
        aviso = db.get(RifaEnumeradaAviso, aviso_id)
        if aviso is None or aviso.estado != "pendiente":
            return

        ok, wamid, error = _enviar_mensaje(http, _LIMITADOR, aviso.celular, _contenido_aviso())
        if ok:
            aviso.estado = "enviado"
            aviso.wamid = wamid
            aviso.enviado_at = datetime.now(timezone.utc)
        else:
            aviso.estado = "error"
            aviso.error = error
        db.commit()

        if ok:
            from app.core.notification_worker import _log_chat

            _log_chat(aviso.celular, "[Notificación WhatsApp] Rifa enumerada: boletas listas, esperando que las solicite", wamid)
    except Exception:
        db.rollback()
        logger.exception("Error enviando el aviso %s", aviso_id)
    finally:
        db.close()


def _finalizar(lote_id: int, motivo_error: str | None = None) -> None:
    db = SessionLocal()
    try:
        if motivo_error:
            db.execute(
                update(RifaEnumeradaAviso)
                .where(RifaEnumeradaAviso.lote_id == lote_id, RifaEnumeradaAviso.estado == "pendiente")
                .values(estado="error", error=f"proceso interrumpido: {motivo_error}"[:300])
            )
        db.execute(
            update(RifaEnumeradaLote)
            .where(RifaEnumeradaLote.id == lote_id)
            .values(estado="finalizado", finalizado_at=datetime.now(timezone.utc))
        )
        db.commit()
    finally:
        db.close()


def _ejecutar_lote(lote_id: int) -> None:
    db = SessionLocal()
    try:
        ids = db.execute(
            select(RifaEnumeradaAviso.id)
            .where(RifaEnumeradaAviso.lote_id == lote_id, RifaEnumeradaAviso.estado == "pendiente")
            .order_by(RifaEnumeradaAviso.id)
        ).scalars().all()
    finally:
        db.close()

    with httpx.Client() as http, ThreadPoolExecutor(max_workers=TRABAJADORES) as pool:
        list(pool.map(lambda aviso_id: _procesar_aviso(aviso_id, http), ids))
    _finalizar(lote_id)


def _ejecutar_seguro(lote_id: int) -> None:
    try:
        _ejecutar_lote(lote_id)
    except Exception as exc:
        logger.exception("Falló el envío del lote %s", lote_id)
        _finalizar(lote_id, str(exc))


def iniciar_lote(lote_id: int) -> None:
    threading.Thread(target=_ejecutar_seguro, args=(lote_id,), daemon=True, name=f"rifa-enum-{lote_id}").start()


def hay_lote_enviando(db: Session) -> bool:
    return db.execute(
        select(func.count()).select_from(RifaEnumeradaLote).where(RifaEnumeradaLote.estado == "enviando")
    ).scalar_one() > 0


def reanudar_lotes() -> None:
    """Al arrancar el pod, retoma los lotes que quedaron enviándose."""
    db = SessionLocal()
    try:
        ids = db.execute(select(RifaEnumeradaLote.id).where(RifaEnumeradaLote.estado == "enviando")).scalars().all()
    finally:
        db.close()
    for lote_id in ids:
        logger.info("Reanudando envío de la rifa enumerada, lote %s", lote_id)
        iniciar_lote(lote_id)


# ── Pagos ─────────────────────────────────────────────────────────────────────

def boletas_por_pagar(db: Session, celular_local: str) -> int:
    return db.execute(
        select(func.count()).select_from(RifaEnumeradaBoleta).where(
            RifaEnumeradaBoleta.celular_local == celular_local,
            RifaEnumeradaBoleta.pagada.is_(False),
            RifaEnumeradaBoleta.retirada.is_(False),
        )
    ).scalar_one()


def marcar_boletas_pagadas(db: Session, celular_local: str, comprobante_num: str, monto: Decimal | None) -> list[str]:
    """Un comprobante paga solo las boletas de un envío (la cantidad de su lote), las más antiguas primero.
    Retorna los números pagados. NO hace commit."""
    sin_pagar = (
        RifaEnumeradaBoleta.celular_local == celular_local,
        RifaEnumeradaBoleta.pagada.is_(False),
        RifaEnumeradaBoleta.retirada.is_(False),
    )
    primera = db.execute(
        select(RifaEnumeradaLote.cantidad)
        .join(RifaEnumeradaBoleta, RifaEnumeradaBoleta.lote_id == RifaEnumeradaLote.id)
        .where(*sin_pagar)
        .order_by(RifaEnumeradaBoleta.id)
        .limit(1)
    ).first()
    if primera is None:
        return []
    filas = db.execute(
        select(RifaEnumeradaBoleta.id, RifaEnumeradaBoleta.numero)
        .where(*sin_pagar)
        .order_by(RifaEnumeradaBoleta.id)
        .limit(max(1, primera[0]))
    ).all()
    db.execute(
        update(RifaEnumeradaBoleta)
        .where(RifaEnumeradaBoleta.id.in_([fila[0] for fila in filas]))
        .values(pagada=True, pagada_at=datetime.now(timezone.utc), comprobante_num=comprobante_num, pago_monto=monto)
    )
    return [fila[1] for fila in filas]


def _texto_numeros(numeros: list[str]) -> str:
    return f"{', '.join(numeros[:-1])} y {numeros[-1]}" if len(numeros) > 1 else numeros[0]


def notificar_pago(celular_local: str, numeros: list[str]) -> None:
    """Encola el aviso de WhatsApp con las boletas que quedaron pagadas."""
    from app.services import notification_queue

    notification_queue.push("rifa_enumerada_pagada", f"57{celular_local}", {"numeros": _texto_numeros(numeros)})


# ── Retiro de boletas ───────────────────────────────────────────────────────────────────────

def devolver_al_pool(db: Session, numeros: list[str]) -> None:
    """Mezcla al azar los números retirados con los que aún no se entregan en esta vuelta. NO hace commit."""
    puntero = db.execute(
        select(Parametro).where(Parametro.clave == KEY_RE_SIGUIENTE).with_for_update()
    ).scalar_one()
    indice = int(puntero.valor) % TOTAL_NUMEROS
    lista = db.execute(select(RifaEnumeradaNumero.numero).order_by(RifaEnumeradaNumero.orden)).scalars().all()

    retirados = set(numeros)
    entregados = [n for n in lista[:indice] if n not in retirados]
    devueltos = [n for n in lista[:indice] if n in retirados]
    if not devueltos:  # ya están en la parte sin entregar
        return
    pendientes = lista[indice:] + devueltos
    random.shuffle(pendientes)

    nueva = entregados + pendientes
    cambios = [{"numero": n, "orden": i} for i, n in enumerate(nueva) if lista[i] != n]
    if cambios:
        db.execute(update(RifaEnumeradaNumero), cambios)
    puntero.valor = str(len(entregados))


def retirar_boletas(db: Session, celular_local: str, boleta_ids: list[int], usuario: str) -> list[RifaEnumeradaBoleta]:
    """Retira boletas enviadas y sin pagar y devuelve sus números al pool. NO hace commit."""
    boletas = db.execute(
        select(RifaEnumeradaBoleta)
        .where(
            RifaEnumeradaBoleta.id.in_(boleta_ids),
            RifaEnumeradaBoleta.celular_local == celular_local,
            RifaEnumeradaBoleta.estado_envio == "enviada",
            RifaEnumeradaBoleta.pagada.is_(False),
            RifaEnumeradaBoleta.retirada.is_(False),
        )
        .order_by(RifaEnumeradaBoleta.id)
    ).scalars().all()
    if not boletas:
        return []
    ahora = datetime.now(timezone.utc)
    for boleta in boletas:
        boleta.retirada = True
        boleta.retirada_at = ahora
        boleta.retirada_por = usuario[:100]
    devolver_al_pool(db, [b.numero for b in boletas])
    return boletas


def notificar_retiro(celular_local: str, numeros: list[str]) -> None:
    """Encola el aviso de WhatsApp con las boletas retiradas."""
    from app.services import notification_queue

    notification_queue.push("rifa_enumerada_retirada", f"57{celular_local}", {"numeros": _texto_numeros(numeros)})


def renombrar_blob_retirada(celular: str, numero: str, boleta_id: int) -> None:
    """Marca con _retirada la copia de la boleta en envios/{celular}/. No interrumpe el retiro si falla."""
    try:
        contenedor = _contenedor()
        origen = contenedor.get_blob_client(_nombre_envio(celular, numero, boleta_id))
        destino = contenedor.get_blob_client(_nombre_envio(celular, numero, boleta_id, retirada=True))
        if destino.start_copy_from_url(origen.url)["copy_status"] == "success":
            origen.delete_blob()
    except Exception:
        logger.warning("No se pudo renombrar la boleta %s de %s como retirada", numero, celular, exc_info=True)


def subir_comprobante(celular_local: str, comprobante_num: str, imagen_b64: str, mime: str) -> None:
    """Guarda el comprobante procesado junto a las boletas del celular. No interrumpe el pago si falla."""
    try:
        from azure.storage.blob import ContentSettings

        datos = base64.b64decode(imagen_b64)
        corto = hashlib.sha1(datos).hexdigest()[:6]
        extension = {"image/png": "png", "image/webp": "webp"}.get(mime, "jpg")
        numero = re.sub(r"[^A-Za-z0-9_-]", "", comprobante_num)[:40] or "sin_numero"
        blob = _contenedor().get_blob_client(f"envios/57{celular_local}/comprobante_{numero}_{corto}.{extension}")
        blob.upload_blob(datos, overwrite=True, content_settings=ContentSettings(content_type=mime))
    except Exception:
        logger.warning("No se pudo subir el comprobante %s de %s", comprobante_num, celular_local, exc_info=True)
