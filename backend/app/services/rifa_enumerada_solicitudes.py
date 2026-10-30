"""Entrega de boletas cuando el cliente pulsa SOLICITAR BOLETAS.

El chatsystem deja la solicitud en Redis (lista COLA, un JSON por solicitud); este consumidor
asigna los números, registra las boletas y las envía como mensajes normales dentro de la ventana de 24 h.
"""
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
import redis
from sqlalchemy import select, update

from app.database import SessionLocal
from app.models.rifa_enumerada import RifaEnumeradaAviso, RifaEnumeradaBase, RifaEnumeradaBoleta, RifaEnumeradaLote
from app.services import rifa_enumerada as svc
from app.services.notification_queue import _get_redis

logger = logging.getLogger(__name__)

COLA = "rifa_enumerada:solicitudes"
COLA_MUERTA = "rifa_enumerada:solicitudes:dead"

_stop = threading.Event()
_pool = ThreadPoolExecutor(max_workers=svc.TRABAJADORES, thread_name_prefix="rifa-entrega")


def _enviar_boleta(boleta_id: int, base: bytes, version: int, contenedor, http: httpx.Client) -> None:
    db = SessionLocal()
    try:
        boleta = db.get(RifaEnumeradaBoleta, boleta_id)
        if boleta is None or boleta.estado_envio != "pendiente":
            return

        try:
            blob = contenedor.get_blob_client(svc._nombre_blob(version, boleta.numero))
            url = blob.url if blob.exists() else svc._subir_imagen(contenedor, version, boleta.numero, base)
        except Exception as exc:
            boleta.estado_envio = "error"
            boleta.error = f"imagen: {exc}"[:300]
            db.commit()
            return

        ok, wamid, error = svc._enviar_mensaje(http, svc._LIMITADOR, boleta.celular, svc.contenido_boleta(url, boleta.numero))
        if ok:
            boleta.estado_envio = "enviada"
            boleta.wamid = wamid
            boleta.enviada_at = datetime.now(timezone.utc)
        else:
            boleta.estado_envio = "error"
            boleta.error = error
        db.commit()

        if ok:
            svc._registrar_envio_en_blob(contenedor, boleta.id, boleta.celular, boleta.numero, url)
            from app.core.notification_worker import _log_chat

            _log_chat(boleta.celular, f"[Notificación WhatsApp] Rifa enumerada: boleta {boleta.numero}", wamid)
    except Exception:
        db.rollback()
        logger.exception("Error enviando la boleta %s", boleta_id)
    finally:
        db.close()


def _entregar(aviso_id: int) -> None:
    db = SessionLocal()
    try:
        base = db.get(RifaEnumeradaBase, svc.BASE_ID)
        if base is None:
            raise RuntimeError("no hay imagen base")
        base_bytes, version = bytes(base.imagen_data), svc.version_base(base)
        ids = db.execute(
            select(RifaEnumeradaBoleta.id)
            .where(RifaEnumeradaBoleta.aviso_id == aviso_id, RifaEnumeradaBoleta.estado_envio == "pendiente")
            .order_by(RifaEnumeradaBoleta.id)
        ).scalars().all()
    finally:
        db.close()
    if not ids:
        return

    contenedor = svc._contenedor()
    with httpx.Client() as http:
        for posicion, boleta_id in enumerate(ids):
            inicio = time.monotonic()
            _enviar_boleta(boleta_id, base_bytes, version, contenedor, http)
            # Meta: 1 mensaje cada 6 s al mismo celular.
            if posicion < len(ids) - 1:
                sobra = svc.ESPACIO_RONDAS_S - (time.monotonic() - inicio)
                if sobra > 0:
                    time.sleep(sobra)


def _entregar_seguro(aviso_id: int) -> None:
    try:
        _entregar(aviso_id)
    except Exception as exc:
        logger.exception("Falló la entrega de boletas del aviso %s", aviso_id)
        db = SessionLocal()
        try:
            db.execute(
                update(RifaEnumeradaBoleta)
                .where(RifaEnumeradaBoleta.aviso_id == aviso_id, RifaEnumeradaBoleta.estado_envio == "pendiente")
                .values(estado_envio="error", error=f"proceso interrumpido: {exc}"[:300])
            )
            db.commit()
        finally:
            db.close()


def procesar_solicitud(celular: str, contexto_wamid: str | None) -> str:
    """Asigna y registra las boletas del aviso al que responde el cliente; el envío sigue en segundo plano."""
    local = re.sub(r"\D", "", celular)[-10:]
    if len(local) != 10:
        return "celular_invalido"

    db = SessionLocal()
    try:
        aviso = None
        if contexto_wamid:
            aviso = db.execute(
                select(RifaEnumeradaAviso)
                .where(RifaEnumeradaAviso.wamid == contexto_wamid, RifaEnumeradaAviso.celular_local == local)
                .with_for_update()
            ).scalar_one_or_none()
        if aviso is None:
            aviso = db.execute(
                select(RifaEnumeradaAviso)
                .where(
                    RifaEnumeradaAviso.celular_local == local,
                    RifaEnumeradaAviso.estado == "enviado",
                    RifaEnumeradaAviso.solicitada_at.is_(None),
                )
                .order_by(RifaEnumeradaAviso.id.desc())
                .limit(1)
                .with_for_update()
            ).scalar_one_or_none()
        if aviso is None:
            return "sin_aviso"
        if aviso.solicitada_at is not None:
            return "ya_solicitada"

        lote = db.get(RifaEnumeradaLote, aviso.lote_id)
        numeros = svc.tomar_numeros(db, max(1, lote.cantidad or 1))
        ahora = datetime.now(timezone.utc)
        db.add_all(
            RifaEnumeradaBoleta(
                lote_id=aviso.lote_id,
                aviso_id=aviso.id,
                celular=aviso.celular,
                celular_local=aviso.celular_local,
                numero=numero,
                ronda=posicion,
                estado_envio="pendiente",
                pagada=False,
                created_at=ahora,
            )
            for posicion, numero in enumerate(numeros, start=1)
        )
        aviso.solicitada_at = ahora
        aviso_id = aviso.id
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    _pool.submit(_entregar_seguro, aviso_id)
    return "entregando"


def reanudar_entregas() -> None:
    """Al arrancar el pod, retoma las boletas que quedaron pendientes de envío."""
    db = SessionLocal()
    try:
        ids = db.execute(
            select(RifaEnumeradaBoleta.aviso_id)
            .where(RifaEnumeradaBoleta.estado_envio == "pendiente", RifaEnumeradaBoleta.aviso_id.is_not(None))
            .distinct()
        ).scalars().all()
    finally:
        db.close()
    for aviso_id in ids:
        logger.info("Reanudando entrega de boletas, aviso %s", aviso_id)
        _pool.submit(_entregar_seguro, aviso_id)


def _consumir() -> None:
    r: redis.Redis = _get_redis()
    logger.info("[RifaSolicitudes] Iniciado")
    while not _stop.is_set():
        try:
            resultado = r.blpop(COLA, timeout=2)
            if resultado is None:
                continue
            _, crudo = resultado
            try:
                mensaje = json.loads(crudo)
                estado = procesar_solicitud(str(mensaje["celular"]), mensaje.get("contexto_wamid") or None)
                logger.info("[RifaSolicitudes] celular=%s -> %s", mensaje["celular"], estado)
            except Exception as exc:
                logger.exception("[RifaSolicitudes] Dead-letter: %s", crudo)
                r.rpush(COLA_MUERTA, json.dumps({
                    "mensaje": crudo,
                    "error": str(exc),
                    "at": datetime.now(timezone.utc).isoformat(),
                }))
        except redis.RedisError:
            logger.exception("[RifaSolicitudes] Error Redis; reintentando en 5 s")
            time.sleep(5)
        except Exception:
            logger.exception("[RifaSolicitudes] Error inesperado en el loop")
            time.sleep(1)
    logger.info("[RifaSolicitudes] Detenido")


def start() -> threading.Thread:
    _stop.clear()
    hilo = threading.Thread(target=_consumir, name="rifa-solicitudes", daemon=True)
    hilo.start()
    return hilo


def stop() -> None:
    _stop.set()
