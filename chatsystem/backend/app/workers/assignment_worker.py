"""
Worker 3 — Assignment Worker

Consumes from  : human_assign_stream
Side effects   : Calls round-robin, writes Assignment to DB,
                 updates Conversation → HUMAN_ACTIVE
                 publishes WebSocket event to assigned agent

If no agent available → conversation stays WAITING_HUMAN,
entry is NOT ACKed for a few retries, then moved to dead-letter.
"""
import asyncio
import logging
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, make_tenant_session
from app.db.tenant import set_tenant_schema
from app.models.conversation import Conversation, ConversationStatus
from app.redis.client import get_redis
from app.redis.streams import (
    HUMAN_ASSIGN_STREAM,
    ASSIGN_CONSUMER_GROUP,
    ensure_consumer_group,
    xadd,
    xreadgroup,
    xack,
    xautoclaim,
)
from app.services.round_robin import assign_agent
from app.websocket.manager import manager

logger = logging.getLogger(__name__)
CONSUMER_NAME = "assign-1"
BATCH = 10
BLOCK_MS = 3000
AUTOCLAIM_IDLE_MS = 45_000
MAX_DELIVERY_COUNT = 5


async def _process_entry(redis, entry_id: str, data: dict, delivery_count: int) -> bool:
    """Returns True if processed (should ACK), False if should retry."""
    tenant_id = data["tenant_id"]
    tenant_slug = data["tenant_slug"]
    conversation_id = uuid.UUID(data["conversation_id"])

    if delivery_count > MAX_DELIVERY_COUNT:
        logger.warning(
            "Conv %s exceeded max delivery attempts — leaving as WAITING_HUMAN",
            conversation_id,
        )
        return True  # ACK to stop processing, stays in WAITING_HUMAN

    schema = f"t_{tenant_slug}"
    set_tenant_schema(schema)

    async with make_tenant_session(schema) as db:
        await db.execute(text(f"SET search_path TO {schema}, public"))

        # Check if still waiting
        conv = await db.scalar(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        if conv is None or conv.status != ConversationStatus.WAITING_HUMAN:
            return True  # Already handled elsewhere

        agent = await assign_agent(redis, db, tenant_slug, conversation_id)

        if agent is None:
            logger.info(
                "No agent available for conv %s (attempt %d/%d)",
                conversation_id, delivery_count, MAX_DELIVERY_COUNT,
            )
            # Do NOT ACK — will be re-delivered after AUTOCLAIM_IDLE_MS
            return False

        # Notify the assigned agent via WebSocket (keyed by slug, matches WS path)
        await manager.publish(tenant_slug, {
            "type": "conversation_assigned",
            "conversation_id": str(conversation_id),
            "agent_id": str(agent.id),
            "phone": data.get("phone", ""),
        })
        logger.info("Assigned conv %s to agent %s", conversation_id, agent.id)
        return True


async def run(stop_event: asyncio.Event) -> None:
    redis = await get_redis()
    manager.set_redis(redis)
    await ensure_consumer_group(redis, HUMAN_ASSIGN_STREAM, ASSIGN_CONSUMER_GROUP)
    logger.info("assignment_worker started")

    while not stop_event.is_set():
        try:
            stuck = await xautoclaim(
                redis, HUMAN_ASSIGN_STREAM, ASSIGN_CONSUMER_GROUP,
                CONSUMER_NAME, AUTOCLAIM_IDLE_MS, count=10,
            )
            for entry_id, data in stuck:
                count = int(data.get("_delivery_count", 1))
                try:
                    ok = await _process_entry(redis, entry_id, data, count)
                    if ok:
                        await xack(redis, HUMAN_ASSIGN_STREAM, ASSIGN_CONSUMER_GROUP, entry_id)
                except Exception:
                    logger.exception("Error in stuck assign entry %s", entry_id)

            entries = await xreadgroup(
                redis, ASSIGN_CONSUMER_GROUP, CONSUMER_NAME,
                HUMAN_ASSIGN_STREAM, count=BATCH, block=BLOCK_MS,
            )
            for entry_id, data in entries:
                count = int(data.get("_delivery_count", 1))
                try:
                    ok = await _process_entry(redis, entry_id, data, count)
                    if ok:
                        await xack(redis, HUMAN_ASSIGN_STREAM, ASSIGN_CONSUMER_GROUP, entry_id)
                except Exception:
                    logger.exception("Error in assign entry %s", entry_id)

        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("assignment_worker loop error")
            await asyncio.sleep(2)

    await redis.aclose()
    logger.info("assignment_worker stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    stop = asyncio.Event()
    asyncio.run(run(stop))
