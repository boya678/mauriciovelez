"""
Worker de notificaciones WhatsApp.
Ejecuta en un thread daemon — arranca desde main.py lifespan.

- Consume notifications:queue con BLPOP (blocking, timeout 2s).
- Rate limit: time.sleep(0.05) entre envíos (~20 msg/s).
- 1 reintento por mensaje antes de moverlo a notifications:dead.
- OTP NO pasa por aquí (es síncrona en auth.py).
"""
import json
import logging
import threading
import time
from datetime import date, datetime, timezone

import httpx
import redis

from app.core.config import settings
from app.services.notification_queue import DEAD_KEY, QUEUE_KEY, _get_redis

logger = logging.getLogger(__name__)

_stop_event = threading.Event()


# ── Funciones de envío ────────────────────────────────────────────────────────

def _wa_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }


def _wa_url() -> str:
    return f"https://graph.facebook.com/v25.0/{settings.WHATSAPP_PHONE_ID}/messages"


def _send_template(numero_dest: str, template: str, components: list) -> None:
    body = {
        "messaging_product": "whatsapp",
        "to": numero_dest,
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": "es_CO"},
            "components": components,
        },
    }
    resp = httpx.post(_wa_url(), json=body, headers=_wa_headers(), timeout=10)
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")


def _dispatch(type: str, celular: str, params: dict) -> None:
    """Despacha el mensaje según su tipo."""
    numero_dest = celular.lstrip("+")

    if type == "nuevo_numero_vip":
        numero = params["numero"]
        metodo = numero[:-3] + numero[-3:][::-1] if len(numero) >= 3 else numero[::-1]
        param_numero = f"{numero} y con el metodo {metodo}"
        valid_until = params["valid_until"]  # str ISO desde la queue
        _send_template(numero_dest, settings.WHATSAPP_TEMPLATE_NOTIFICACION_NUMERO_VIP, [
            {"type": "body", "parameters": [
                {"type": "text", "text": param_numero},
                {"type": "text", "text": date.fromisoformat(valid_until).strftime("%d/%m/%Y")},
            ]},
        ])

    elif type == "nuevo_numero_free":
        numero = params["numero"]
        metodo = numero[:-3] + numero[-3:][::-1] if len(numero) >= 3 else numero[::-1]
        param_numero = f"{numero} y con el metodo {metodo}"
        valid_until = params["valid_until"]
        _send_template(numero_dest, settings.WHATSAPP_TEMPLATE_NOTIFICACION_NUMERO_FREE, [
            {"type": "body", "parameters": [
                {"type": "text", "text": param_numero},
                {"type": "text", "text": date.fromisoformat(valid_until).strftime("%d/%m/%Y")},
            ]},
        ])

    elif type == "ganador_vip":
        numero = params["numero"]
        devuelto = numero[:-3] + numero[-3:][::-1] if len(numero) >= 3 else numero
        _send_template(numero_dest, settings.WHATSAPP_TEMPLATE_GANADOR_VIP, [
            {"type": "body", "parameters": [
                {"type": "text", "text": f"{numero} {devuelto}"},
                {"type": "text", "text": f"{params['loteria']} {params['resultado_num']}"},
            ]},
        ])

    elif type == "ganador_free":
        numero = params["numero"]
        devuelto = numero[:-3] + numero[-3:][::-1] if len(numero) >= 3 else numero
        _send_template(numero_dest, settings.WHATSAPP_TEMPLATE_GANADOR_FREE, [
            {"type": "body", "parameters": [
                {"type": "text", "text": f"{numero} {devuelto}"},
                {"type": "text", "text": f"{params['loteria']} {params['resultado_num']}"},
            ]},
        ])

    elif type == "recordatorio_vencimiento":
        _send_template(numero_dest, settings.WHATSAPP_VENCIMIENTO_VIP, [])

    elif type == "codigo_cliente":
        codigo = params["codigo_vip"]
        _send_template(numero_dest, settings.WHATSAPP_TEMPLATE_CODIGO, [
            {"type": "body", "parameters": [
                {"type": "text", "text": codigo},
            ]},
        ])

    else:
        logger.warning("Tipo de notificación desconocido: %s", type)


# ── Loop principal ────────────────────────────────────────────────────────────

def _worker_loop() -> None:
    r: redis.Redis = _get_redis()
    logger.info("[NotifWorker] Iniciado")

    while not _stop_event.is_set():
        try:
            result = r.blpop(QUEUE_KEY, timeout=2)
            if result is None:
                continue  # timeout — volver a chequear _stop_event

            _, raw = result
            msg = json.loads(raw)
            type_ = msg["type"]
            celular = msg["celular"]
            params = msg["params"]

            # Intento 1
            try:
                _dispatch(type_, celular, params)
                logger.info("[NotifWorker] Enviado type=%s celular=%s", type_, celular)
            except Exception as e1:
                logger.warning("[NotifWorker] Fallo 1/2 type=%s celular=%s: %s", type_, celular, e1)
                time.sleep(1)
                # Intento 2 (reintento)
                try:
                    _dispatch(type_, celular, params)
                    logger.info("[NotifWorker] Enviado (retry) type=%s celular=%s", type_, celular)
                except Exception as e2:
                    logger.error(
                        "[NotifWorker] Dead-letter type=%s celular=%s error=%s",
                        type_, celular, e2,
                    )
                    import datetime as _dt
                    msg["dead_reason"] = str(e2)
                    msg["dead_at"] = datetime.now(timezone.utc).isoformat()
                    r.rpush(DEAD_KEY, json.dumps(msg))

            time.sleep(0.05)  # rate limit ~20 msg/s

        except redis.RedisError:
            logger.exception("[NotifWorker] Error Redis — reintentando en 5s")
            time.sleep(5)
        except Exception:
            logger.exception("[NotifWorker] Error inesperado en loop")
            time.sleep(1)

    logger.info("[NotifWorker] Detenido")


def start() -> threading.Thread:
    """Arranca el worker en un thread daemon. Llamar desde main.py lifespan."""
    _stop_event.clear()
    t = threading.Thread(target=_worker_loop, name="notif-worker", daemon=True)
    t.start()
    return t


def stop() -> None:
    """Señala al worker que se detenga. El thread termina en ≤3s."""
    _stop_event.set()
