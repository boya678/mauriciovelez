"""
Cola de notificaciones WhatsApp usando Redis List.
Productores: push() — encolan un mensaje JSON.
Consumidor: notification_worker.py — hace BLPOP y envía.

OTP NO pasa por aquí — es síncrona en auth.py.
"""
import json
import logging
from datetime import date
from typing import Any

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

QUEUE_KEY = "notifications:queue"
DEAD_KEY = "notifications:dead"

_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def push(type: str, celular: str, params: dict[str, Any]) -> None:
    """Encola una notificación WhatsApp. Serializa dates a string ISO."""
    payload: dict[str, Any] = {"type": type, "celular": celular, "params": {}}
    for k, v in params.items():
        payload["params"][k] = v.isoformat() if isinstance(v, date) else v
    try:
        _get_redis().rpush(QUEUE_KEY, json.dumps(payload))
    except Exception:
        logger.exception("Error al encolar notificación type=%s celular=%s", type, celular)
