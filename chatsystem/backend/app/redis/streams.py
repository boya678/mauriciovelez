"""
Redis Streams helpers.

Global stream names (tenant_id is included as a field inside each message).
"""
import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

# ----------- Stream name constants -----------
MESSAGES_STREAM = "messages_stream"
AI_STREAM = "ai_processing_stream"
HUMAN_ASSIGN_STREAM = "human_assign_stream"
OUTGOING_STREAM = "outgoing_stream"

# ----------- Consumer group constants -----------
MSG_CONSUMER_GROUP = settings.STREAM_CONSUMER_GROUP
AI_CONSUMER_GROUP = settings.AI_CONSUMER_GROUP
ASSIGN_CONSUMER_GROUP = settings.ASSIGN_CONSUMER_GROUP
OUTGOING_CONSUMER_GROUP = settings.OUTGOING_CONSUMER_GROUP

# ----------- Legacy per-tenant builder functions (kept for reference) -----------
def s_messages(tenant_id: str) -> str:
    return f"{tenant_id}:messages_stream"

def s_ai(tenant_id: str) -> str:
    return f"{tenant_id}:ai_processing_stream"

def s_assign(tenant_id: str) -> str:
    return f"{tenant_id}:human_assign_stream"

def s_outgoing(tenant_id: str) -> str:
    return f"{tenant_id}:outgoing_stream"


async def xadd(redis: aioredis.Redis, stream: str, data: dict[str, Any]) -> str:
    """Add event to stream. All values are JSON-serialised so _try_json round-trips correctly."""
    flat = {k: json.dumps(v) for k, v in data.items()}
    msg_id = await redis.xadd(stream, flat, maxlen=50_000, approximate=True)
    logger.debug("XADD %s -> %s", stream, msg_id)
    return msg_id


async def ensure_consumer_group(
    redis: aioredis.Redis, stream: str, group: str
) -> None:
    """Create consumer group if it doesn't exist."""
    try:
        await redis.xgroup_create(stream, group, id="0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" in str(exc):
            pass  # already exists
        else:
            raise


async def xreadgroup(
    redis: aioredis.Redis,
    group: str,
    consumer: str,
    stream: str,
    count: int = 10,
    block: int = 2000,
) -> list[tuple[str, dict]]:
    """Read pending messages from group. Returns list of (msg_id, fields)."""
    results = await redis.xreadgroup(
        groupname=group,
        consumername=consumer,
        streams={stream: ">"},
        count=count,
        block=block,
    )
    if not results:
        return []
    messages = []
    for _stream, entries in results:
        for msg_id, fields in entries:
            decoded = {k: _try_json(v) for k, v in fields.items()}
            messages.append((msg_id, decoded))
    return messages


async def xack(redis: aioredis.Redis, stream: str, group: str, msg_id: str) -> None:
    await redis.xack(stream, group, msg_id)


async def xautoclaim(
    redis: aioredis.Redis,
    stream: str,
    group: str,
    consumer: str,
    min_idle_ms: int = 60_000,
    count: int = 10,
) -> list[tuple[str, dict]]:
    """Reclaim messages idle > min_idle_ms (for retry/dead-letter handling)."""
    try:
        result = await redis.xautoclaim(stream, group, consumer, min_idle_ms, count=count)
        messages = []
        for msg_id, fields in result[1]:
            decoded = {k: _try_json(v) for k, v in fields.items()}
            messages.append((msg_id, decoded))
        return messages
    except Exception as exc:
        logger.warning("xautoclaim failed: %s", exc)
        return []


def _try_json(v: str) -> Any:
    try:
        return json.loads(v)
    except (json.JSONDecodeError, TypeError):
        return v
