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
from app.services.servicios_config import get_rifa_enumerada_entrega_abierta

logger = logging.getLogger(__name__)

COLA = "rifa_enumerada:solicitudes"
COLA_MUERTA = "rifa_enumerada:solicitudes:dead"

_stop = threading.Event()
_pool = ThreadPoolExecutor(max_workers=svc.TRABAJADORES, thread_name_prefix="rifa-entrega")


def _enviar_boleta(boleta_id: int, base: bytes, version: int, contenedor, http: httpx.Client, reenviar: bool = False) -> None:
    db = SessionLocal()
    try:
        boleta = db.get(RifaEnumeradaBoleta, boleta_id)
        if boleta is None or (not reenviar and boleta.estado_envio != "pendiente"):
            return
        nota = ("Pagada" if boleta.pagada else "Pendiente de pago") if reenviar else None

        def fallo(motivo: str) -> None:
            # Un reenvío fallido no quita el estado de una boleta que el cliente ya recibió.
            if reenviar:
                boleta.error = f"reenvío: {motivo}"[:300]
            else:
                boleta.estado_envio = "error"
                boleta.error = motivo[:300]

        try:
            blob = contenedor.get_blob_client(svc._nombre_blob(version, boleta.numero))
            url = blob.url if blob.exists() else svc._subir_imagen(contenedor, version, boleta.numero, base)
        except Exception as exc:
            fallo(f"imagen: {exc}")
            db.commit()
            return

        ok, wamid, error = svc._enviar_mensaje(http, svc._LIMITADOR, boleta.celular, svc.contenido_boleta(url, boleta.numero, nota))
        if ok:
            if reenviar:
                boleta.error = None
            else:
                boleta.estado_envio = "enviada"
                boleta.wamid = wamid
                boleta.enviada_at = datetime.now(timezone.utc)
        else:
            fallo(error or "sin respuesta")
        db.commit()

        if ok:
            svc._registrar_envio_en_blob(contenedor, boleta.id, boleta.celular, boleta.numero, url)
            from app.core.notification_worker import _log_chat

            detalle = f" (reenvío, {nota.lower()})" if reenviar else ""
            _log_chat(boleta.celular, f"[Notificación WhatsApp] Rifa enumerada: boleta {boleta.numero}{detalle}", wamid)
    except Exception:
        db.rollback()
        logger.exception("Error enviando la boleta %s", boleta_id)
    finally:
        db.close()


def _entregar_ids(ids: list[int], reenviar: bool = False) -> None:
    """Envía las boletas de un mismo celular, una tras otra."""
    if not ids:
        return
    db = SessionLocal()
    try:
        base = db.get(RifaEnumeradaBase, svc.BASE_ID)
        if base is None:
            raise RuntimeError("no hay imagen base")
        base_bytes, version = bytes(base.imagen_data), svc.version_base(base)
    finally:
        db.close()

    contenedor = svc._contenedor()
    with httpx.Client() as http:
        for posicion, boleta_id in enumerate(ids):
            inicio = time.monotonic()
            _enviar_boleta(boleta_id, base_bytes, version, contenedor, http, reenviar)
            # Meta: 1 mensaje cada 6 s al mismo celular.
            if posicion < len(ids) - 1:
                sobra = svc.ESPACIO_RONDAS_S - (time.monotonic() - inicio)
                if sobra > 0:
                    time.sleep(sobra)


def _entregar_ids_seguro(ids: list[int], reenviar: bool = False) -> None:
    try:
        _entregar_ids(ids, reenviar)
    except Exception as exc:
        logger.exception("Falló la entrega de boletas %s", ids)
        if reenviar:
            return
        db = SessionLocal()
        try:
            db.execute(
                update(RifaEnumeradaBoleta)
                .where(RifaEnumeradaBoleta.id.in_(ids), RifaEnumeradaBoleta.estado_envio == "pendiente")
                .values(estado_envio="error", error=f"proceso interrumpido: {exc}"[:300])
            )
            db.commit()
        finally:
            db.close()


def entregar_en_segundo_plano(ids: list[int], reenviar: bool = False) -> None:
    _pool.submit(_entregar_ids_seguro, ids, reenviar)


MENSAJE_RONDA_FINALIZADA = (
    "La ronda de boletería ya finalizó. Próximamente te enviaremos de nuevo el mensaje para solicitar más boletas."
)


def _avisar_ronda_finalizada(celular: str) -> None:
    """Respuesta a quien pulsa el botón con la entrega cerrada; a lo sumo una vez por hora por celular."""
    try:
        if not _get_redis().set(f"rifa_enumerada:cierre:{celular}", "1", nx=True, ex=3600):
            return
        with httpx.Client() as http:
            ok, wamid, error = svc._enviar_mensaje(
                http, svc._LIMITADOR, celular, {"type": "text", "text": {"body": MENSAJE_RONDA_FINALIZADA}}
            )
        if not ok:
            logger.warning("No se pudo avisar la ronda finalizada a %s: %s", celular, error)
            return
        from app.core.notification_worker import _log_chat

        _log_chat(celular, "[Notificación WhatsApp] Rifa enumerada: ronda finalizada, se le avisó que se enviará un nuevo mensaje", wamid)
    except Exception:
        logger.exception("Error avisando la ronda finalizada a %s", celular)


def procesar_solicitud(celular: str, contexto_wamid: str | None) -> str:
    """Asigna y registra las boletas del aviso al que responde el cliente; el envío sigue en segundo plano."""
    local = re.sub(r"\D", "", celular)[-10:]
    if len(local) != 10:
        return "celular_invalido"

    db = SessionLocal()
    try:
        if not get_rifa_enumerada_entrega_abierta(db):
            hubo_aviso = db.execute(
                select(RifaEnumeradaAviso.id)
                .where(RifaEnumeradaAviso.celular_local == local, RifaEnumeradaAviso.estado == "enviado")
                .limit(1)
            ).first() is not None
            if hubo_aviso:
                _pool.submit(_avisar_ronda_finalizada, f"57{local}")
            return "ronda_cerrada" if hubo_aviso else "sin_aviso"

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
        boletas = [
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
        ]
        db.add_all(boletas)
        aviso.solicitada_at = ahora
        db.flush()
        ids = [b.id for b in boletas]
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    entregar_en_segundo_plano(ids)
    return "entregando"


def reanudar_entregas() -> None:
    """Al arrancar el pod, retoma las boletas que quedaron pendientes de envío."""
    db = SessionLocal()
    try:
        pendientes = db.execute(
            select(RifaEnumeradaBoleta.celular_local, RifaEnumeradaBoleta.id)
            .where(RifaEnumeradaBoleta.estado_envio == "pendiente")
            .order_by(RifaEnumeradaBoleta.id)
        ).all()
    finally:
        db.close()
    por_celular: dict[str, list[int]] = {}
    for celular_local, boleta_id in pendientes:
        por_celular.setdefault(celular_local, []).append(boleta_id)
    for celular_local, ids in por_celular.items():
        logger.info("Reanudando entrega de %s boletas pendientes de %s", len(ids), celular_local)
        entregar_en_segundo_plano(ids)


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
