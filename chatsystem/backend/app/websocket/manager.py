"""
WebSocket connection manager with Redis Pub/Sub bridge.

Each agent connects via WebSocket to:
  /ws/tenant/{tenant_id}/agent/{agent_id}

The manager:
  - Tracks active WS connections per (tenant_id, agent_id)
  - Subscribes to Redis channel "chat_events:{tenant_id}"
  - Forwards published events to all connected agents of that tenant
  - Handles graceful disconnection

Events flow:
  Worker publishes → Redis pubsub → manager.broadcast → WebSocket → Angular
"""
import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

import redis.asyncio as aioredis
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        # { tenant_id: { agent_id: WebSocket } }
        self._connections: dict[str, dict[str, WebSocket]] = defaultdict(dict)
        # { tenant_id: asyncio.Task }
        self._subscriber_tasks: dict[str, asyncio.Task] = {}
        self._redis: aioredis.Redis | None = None

    def set_redis(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    # ── Connection lifecycle ─────────────────────────────────────────────────

    async def connect(
        self,
        websocket: WebSocket,
        tenant_id: str,
        agent_id: str,
    ) -> None:
        await websocket.accept()
        self._connections[tenant_id][agent_id] = websocket
        logger.info("Agent %s connected (tenant %s)", agent_id, tenant_id)

        # Start subscriber for this tenant if not running
        if tenant_id not in self._subscriber_tasks or self._subscriber_tasks[tenant_id].done():
            task = asyncio.create_task(
                self._subscribe_tenant(tenant_id),
                name=f"pubsub:{tenant_id}",
            )
            self._subscriber_tasks[tenant_id] = task

    async def disconnect(self, tenant_id: str, agent_id: str) -> None:
        self._connections[tenant_id].pop(agent_id, None)
        logger.info("Agent %s disconnected (tenant %s)", agent_id, tenant_id)

        # If no more connections for this tenant, cancel subscriber task
        if not self._connections[tenant_id]:
            del self._connections[tenant_id]
            task = self._subscriber_tasks.pop(tenant_id, None)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    # ── Publish (called by workers/services) ─────────────────────────────────

    async def publish(self, tenant_id: str, event: dict[str, Any]) -> None:
        """Publish an event to all agents of the given tenant via Redis Pub/Sub."""
        if self._redis is None:
            return
        channel = f"chat_events:{tenant_id}"
        await self._redis.publish(channel, json.dumps(event))

    # ── Broadcast to local connections ────────────────────────────────────────

    async def broadcast(
        self,
        tenant_id: str,
        message: dict[str, Any],
        exclude_agent_id: str | None = None,
    ) -> None:
        """Send event to all connected agents of a tenant in this instance."""
        dead: list[str] = []
        for agent_id, ws in list(self._connections.get(tenant_id, {}).items()):
            if agent_id == exclude_agent_id:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                logger.warning("Send failed to agent %s, marking for removal", agent_id)
                dead.append(agent_id)
        for agent_id in dead:
            await self.disconnect(tenant_id, agent_id)

    async def send_to_agent(
        self,
        tenant_id: str,
        agent_id: str,
        message: dict[str, Any],
    ) -> bool:
        """Send directly to a specific agent. Returns True if sent."""
        ws = self._connections.get(tenant_id, {}).get(agent_id)
        if ws is None:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            await self.disconnect(tenant_id, agent_id)
            return False

    # ── Internal subscriber task ──────────────────────────────────────────────

    async def _subscribe_tenant(self, tenant_id: str) -> None:
        if self._redis is None:
            return
        channel = f"chat_events:{tenant_id}"
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        logger.info("Subscribed to Redis channel: %s", channel)
        try:
            async for raw in pubsub.listen():
                if raw["type"] != "message":
                    continue
                try:
                    data = json.loads(raw["data"])
                except (ValueError, TypeError):
                    continue
                await self.broadcast(tenant_id, data)
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            logger.info("Unsubscribed from Redis channel: %s", channel)


# Singleton instance — imported by routes and workers
manager = ConnectionManager()
