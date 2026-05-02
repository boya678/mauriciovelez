"""
WebSocket endpoint

ws://{host}/ws/{tenant_id}/{agent_id}?token=<JWT>

Flow:
  1. Validate JWT (agent must belong to tenant)
  2. Register connection in manager
  3. Set agent ONLINE in Redis
  4. Receive messages from client (heartbeat pings, typing events)
  5. Forward events from manager to client
  6. On disconnect: set OFFLINE + deregister
"""
import json
import logging
import uuid

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select, update

from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal, make_tenant_session
from app.db.tenant import set_tenant_schema
from app.models.agent import Agent, AgentStatus
from app.redis.client import get_redis
from app.services.round_robin import refresh_presence, set_agent_online, set_agent_offline
from app.websocket.manager import manager

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)


@router.websocket("/ws/{tenant_id}/{agent_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    tenant_id: str,
    agent_id: str,
    token: str = Query(...),
):
    # 1. Validate JWT
    payload = decode_access_token(token)
    if payload is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    # Path carries tenant_slug (e.g. "mauriciovelez"), not the UUID
    token_tenant_slug = payload.get("tenant_slug", "")
    token_agent = payload.get("sub", "")

    if token_tenant_slug != tenant_id or token_agent != agent_id:
        await websocket.close(code=4003, reason="Token mismatch")
        return

    # tenant_id in path IS the slug — rename for clarity
    tenant_slug = tenant_id
    schema = f"t_{tenant_slug}"
    agent_uuid = uuid.UUID(agent_id)

    # 2. Connect
    redis = await get_redis()
    manager.set_redis(redis)
    await manager.connect(websocket, tenant_slug, agent_id)

    # 3. Set agent ONLINE in Redis + DB
    await set_agent_online(redis, tenant_slug, agent_id)
    async with make_tenant_session(schema) as db:
        await db.execute(
            update(Agent).where(Agent.id == agent_uuid).values(status=AgentStatus.ONLINE)
        )
        await db.commit()

    try:
        async for raw in websocket.iter_text():
            try:
                msg = json.loads(raw)
            except ValueError:
                continue

            event_type = msg.get("type")

            if event_type == "ping":
                await refresh_presence(redis, tenant_slug, agent_id)
                await websocket.send_json({"type": "pong"})

            elif event_type == "typing":
                # Forward typing indicator to channel
                await manager.publish(tenant_slug, {
                    "type": "agent_typing",
                    "conversation_id": msg.get("conversation_id"),
                    "agent_id": agent_id,
                })

    except WebSocketDisconnect:
        logger.info("Agent %s disconnected from tenant %s", agent_id, tenant_slug)
    finally:
        await manager.disconnect(tenant_slug, agent_id)
        await set_agent_offline(redis, tenant_slug, agent_id)
        async with make_tenant_session(schema) as db:
            await db.execute(
                update(Agent).where(Agent.id == agent_uuid).values(status=AgentStatus.OFFLINE)
            )
            await db.commit()
