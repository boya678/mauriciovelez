"""Servicio 'Rifa enumerada': boletas con número (0000-9999 barajado) enviadas por WhatsApp."""
import hashlib
import logging
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
from app.models.rifa_enumerada import RifaEnumeradaBase, RifaEnumeradaBoleta, RifaEnumeradaLote, RifaEnumeradaNumero
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


def _enviar_plantilla(http: httpx.Client, limitador: _Limitador, celular: str, numero: str, url_imagen: str):
    """Retorna (ok, wamid, error)."""
    cuerpo = {
        "messaging_product": "whatsapp",
        "to": celular,
        "type": "template",
        "template": {
            "name": settings.WHATSAPP_TEMPLATE_NOTIFICACION_RIFA_ENUMERADA,
            "language": {"code": "es_CO"},
            "components": [
                {"type": "header", "parameters": [{"type": "image", "image": {"link": url_imagen}}]},
                {"type": "body", "parameters": [{"type": "text", "text": numero}]},
            ],
        },
    }
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


def _registrar_envio_en_blob(contenedor, boleta_id: int, celular: str, numero: str, url_origen: str) -> None:
    """Deja la boleta enviada en envios/{celular}/ para consultarla por número de WhatsApp."""
    # El hash sale del id de la boleta: un mismo número reenviado al mismo celular no se pisa.
    corto = hashlib.sha1(str(boleta_id).encode()).hexdigest()[:6]
    try:
        contenedor.get_blob_client(f"envios/{celular}/{numero}_{corto}.jpg").start_copy_from_url(url_origen)
    except Exception:
        logger.warning("No se pudo copiar la boleta %s de %s a envios/", numero, celular, exc_info=True)


def _procesar_boleta(boleta_id: int, ctx: dict) -> None:
    db = SessionLocal()
    try:
        boleta = db.get(RifaEnumeradaBoleta, boleta_id)
        if boleta is None or boleta.estado_envio != "pendiente":
            return

        nombre = _nombre_blob(ctx["version"], boleta.numero)
        try:
            if nombre not in ctx["existentes"]:
                url = _subir_imagen(ctx["contenedor"], ctx["version"], boleta.numero, ctx["base"])
                ctx["existentes"].add(nombre)
            else:
                url = f"{ctx['contenedor'].url}/{nombre}"
        except Exception as exc:
            boleta.estado_envio = "error"
            boleta.error = f"imagen: {exc}"[:300]
            db.commit()
            return

        ok, wamid, error = _enviar_plantilla(ctx["http"], ctx["limitador"], boleta.celular, boleta.numero, url)
        if ok:
            boleta.estado_envio = "enviada"
            boleta.wamid = wamid
            boleta.enviada_at = datetime.now(timezone.utc)
        else:
            boleta.estado_envio = "error"
            boleta.error = error
        db.commit()

        if ok:
            _registrar_envio_en_blob(ctx["contenedor"], boleta.id, boleta.celular, boleta.numero, url)
            from app.core.notification_worker import _log_chat

            _log_chat(boleta.celular, f"[Notificación WhatsApp] Rifa enumerada: boleta {boleta.numero}", wamid)
    except Exception:
        db.rollback()
        logger.exception("Error procesando boleta %s", boleta_id)
    finally:
        db.close()


def _finalizar(lote_id: int, motivo_error: str | None = None) -> None:
    db = SessionLocal()
    try:
        if motivo_error:
            db.execute(
                update(RifaEnumeradaBoleta)
                .where(RifaEnumeradaBoleta.lote_id == lote_id, RifaEnumeradaBoleta.estado_envio == "pendiente")
                .values(estado_envio="error", error=f"proceso interrumpido: {motivo_error}"[:300])
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
        base = db.get(RifaEnumeradaBase, BASE_ID)
        if base is None:
            raise RuntimeError("no hay imagen base")
        base_bytes, version = bytes(base.imagen_data), version_base(base)
        rondas: dict[int, list[int]] = {}
        for boleta_id, ronda in db.execute(
            select(RifaEnumeradaBoleta.id, RifaEnumeradaBoleta.ronda)
            .where(RifaEnumeradaBoleta.lote_id == lote_id, RifaEnumeradaBoleta.estado_envio == "pendiente")
            .order_by(RifaEnumeradaBoleta.ronda, RifaEnumeradaBoleta.id)
        ).all():
            rondas.setdefault(ronda, []).append(boleta_id)
    finally:
        db.close()

    contenedor = _contenedor()
    prefijo = f"boletas/v{version}/"
    ctx = {
        "base": base_bytes,
        "version": version,
        "contenedor": contenedor,
        "existentes": {b.name for b in contenedor.list_blobs(name_starts_with=prefijo)},
        "limitador": _Limitador(MAX_MPS),
        "http": httpx.Client(),
    }
    try:
        orden = sorted(rondas)
        for posicion, ronda in enumerate(orden):
            inicio = time.monotonic()
            with ThreadPoolExecutor(max_workers=TRABAJADORES) as pool:
                list(pool.map(lambda bid: _procesar_boleta(bid, ctx), rondas[ronda]))
            # Cada celular recibe su siguiente boleta con al menos 6 s de diferencia.
            if posicion < len(orden) - 1:
                sobra = ESPACIO_RONDAS_S - (time.monotonic() - inicio)
                if sobra > 0:
                    time.sleep(sobra)
    finally:
        ctx["http"].close()
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
        )
    ).scalar_one()


def marcar_boletas_pagadas(db: Session, celular_local: str, comprobante_num: str, monto: Decimal | None) -> int:
    """Marca como pagadas todas las boletas pendientes de pago del celular. NO hace commit."""
    resultado = db.execute(
        update(RifaEnumeradaBoleta)
        .where(RifaEnumeradaBoleta.celular_local == celular_local, RifaEnumeradaBoleta.pagada.is_(False))
        .values(pagada=True, pagada_at=datetime.now(timezone.utc), comprobante_num=comprobante_num, pago_monto=monto)
    )
    return resultado.rowcount
