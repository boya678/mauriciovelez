"""
Cross-worker / cross-pod invalidation of the in-process tenant cache.

Every backend process keeps its own `_tenant_cache` (slug/id -> TenantContext)
for low-latency lookups. When tenant settings are updated (prompt, template,
webhook secret, etc.) we need *every* process to drop its cached entry so it
re-reads from the DB on the next request.

Mechanism: Redis Pub/Sub on channel `tenant:invalidate`. Each backend process
subscribes during startup and removes the published key from its local cache.

Publishers call `publish_tenant_invalidate(redis, slug, id, ...)` after the DB
commit. The publisher also clears its own local cache immediately so the
response on the same request already reflects fresh data.
"""
from __future__ import annotations

import asyncio
import logging

from app.db.tenant import _tenant_cache

logger = logging.getLogger(__name__)

CHANNEL = "tenant:invalidate"


async def publish_tenant_invalidate(redis, *keys: str) -> None:
    """Broadcast invalidation for one or more cache keys (slug and/or id)."""
    for k in keys:
        if not k:
            continue
        # Clear local cache right away so the current process is consistent.
        _tenant_cache.pop(k, None)
        try:
            await redis.publish(CHANNEL, k)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to publish tenant invalidation for %s: %s", k, exc)


async def _listen(redis) -> None:
    pubsub = redis.pubsub()
    await pubsub.subscribe(CHANNEL)
    logger.info("Tenant cache invalidation listener subscribed on %s", CHANNEL)
    try:
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            key = msg.get("data")
            if isinstance(key, bytes):
                key = key.decode()
            if key:
                _tenant_cache.pop(key, None)
                logger.info("Invalidated local tenant cache key: %s", key)
    except asyncio.CancelledError:
        try:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()
        except Exception:  # noqa: BLE001
            pass
        raise


def start_invalidation_listener(redis) -> asyncio.Task:
    return asyncio.create_task(_listen(redis), name="tenant-cache-invalidation")
