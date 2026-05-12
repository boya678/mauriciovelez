"""WebSocket endpoint para la vista en vivo con historial persistido en Redis."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.live_events import CHANNEL, _get_client, get_history

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/live", tags=["live"])


@router.websocket("/ws")
async def live_ws(websocket: WebSocket):
    """WebSocket público para la vista en vivo.

    Al conectar: envía el historial reciente (hasta 50 eventos) en orden cronológico.
    Luego: suscribe al canal Redis y reenvía cada mensaje en tiempo real.
    """
    await websocket.accept()
    loop = asyncio.get_event_loop()

    # 1) Enviar historial al conectar
    try:
        history = await loop.run_in_executor(None, lambda: get_history(50))
        for item in history:
            await websocket.send_text(item)
    except Exception:
        logger.warning("live_ws: error enviando historial")

    # 2) Suscribirse a Redis pub/sub
    client = _get_client()
    pubsub = client.pubsub()
    try:
        await loop.run_in_executor(None, lambda: pubsub.subscribe(CHANNEL))

        while True:
            # get_message bloqueante → ejecutamos en threadpool con timeout corto
            msg = await loop.run_in_executor(
                None,
                lambda: pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
            )
            if msg and msg.get("type") == "message":
                data = msg["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="ignore")
                await websocket.send_text(data)
            else:
                # keepalive ligero: ping de aplicación cada ~20 s lo gestiona el cliente,
                # pero forzamos cooperación para no monopolizar el loop
                await asyncio.sleep(0)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("live_ws: error inesperado")
    finally:
        try:
            await loop.run_in_executor(None, lambda: pubsub.unsubscribe(CHANNEL))
            await loop.run_in_executor(None, pubsub.close)
        except Exception:
            pass

