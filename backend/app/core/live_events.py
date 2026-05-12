"""Utilidad para publicar eventos en tiempo real via Redis pub/sub + historial."""
from __future__ import annotations

import json
import logging
import time

import redis as _redis_lib

from app.core.config import settings

logger = logging.getLogger(__name__)

CHANNEL = "live:eventos"
HISTORY_KEY = "live:eventos:history"

_client: _redis_lib.Redis | None = None


def _get_client() -> _redis_lib.Redis:
    global _client
    if _client is None:
        _client = _redis_lib.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
    return _client


def publish_event(tipo: str, data: dict) -> None:
    """Publica un evento en el sorted set de historial (score = ts) y al canal pub/sub.

    Los eventos más antiguos que HISTORY_TTL se eliminan automáticamente con cada
    publicación. Nunca lanza excepción.
    """
    try:
        ts = time.time()
        payload = json.dumps({"tipo": tipo, "ts": ts, **data}, ensure_ascii=False)
        cutoff = ts - settings.REDIS_TTL
        client = _get_client()
        pipe = client.pipeline()
        # Insertar en sorted set con timestamp como score
        pipe.zadd(HISTORY_KEY, {payload: ts})
        # Limpiar entradas más antiguas que el TTL
        pipe.zremrangebyscore(HISTORY_KEY, "-inf", cutoff)
        # Publicar al canal pub/sub
        pipe.publish(CHANNEL, payload)
        pipe.execute()
    except Exception:
        logger.warning("live_events: no se pudo publicar evento '%s'", tipo)


def get_history(limit: int = 50) -> list[str]:
    """Devuelve los últimos `limit` eventos vigentes, en orden cronológico."""
    try:
        # zrange con rev=False y score -inf/+inf devuelve cronológicamente
        # Pedimos solo los últimos `limit` usando zrange con rev=True y luego invertimos
        items = _get_client().zrange(HISTORY_KEY, -limit, -1)
        return list(items)  # ya vienen en orden cronológico (score asc)
    except Exception:
        logger.warning("live_events: no se pudo leer historial")
        return []
