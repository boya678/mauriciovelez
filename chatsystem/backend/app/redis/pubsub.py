"""
Redis Pub/Sub for broadcasting events across backend instances.

Channel: chat_events:{tenant_id}

Event payload (JSON):
{
  "event": "new_message" | "conversation_updated" | "agent_assigned",
  "tenant_id": "...",
  "data": { ... }
}
"""
import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "chat_events"


def channel(tenant_id: str) -> str:
    return f"{CHANNEL_PREFIX}:{tenant_id}"


async def publish(redis: aioredis.Redis, tenant_id: str, event: str, data: dict[str, Any]) -> None:
    payload = json.dumps({"event": event, "tenant_id": tenant_id, "data": data})
    await redis.publish(channel(tenant_id), payload)
    logger.debug("PUB %s -> %s", channel(tenant_id), event)


async def subscribe_loop(
    redis_url: str,
    tenant_id: str,
    handler: Callable[[str, dict], Coroutine],
) -> None:
    """
    Runs forever. Creates its own connection (pubsub requires dedicated connection).
    Call in asyncio.create_task().
    """
    client = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(channel(tenant_id))
    logger.info("Subscribed to %s", channel(tenant_id))
    try:
        async for raw in pubsub.listen():
            if raw["type"] != "message":
                continue
            try:
                payload = json.loads(raw["data"])
                await handler(payload["event"], payload.get("data", {}))
            except Exception:
                logger.exception("Error handling pubsub message")
    finally:
        await pubsub.unsubscribe()
        await client.aclose()
