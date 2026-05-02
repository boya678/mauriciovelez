"""
Round-robin agent assignment with Redis + DB validation.

Redis key: agents_queue:{tenant_id}  (type: List of agent UUID strings)

Algorithm:
  1. Acquire conversation lock (SET NX EX)
  2. RPOPLPUSH rotate queue
  3. Validate: agent ONLINE (Redis) + has capacity (DB)
  4. Assign in DB transaction
  5. Release lock on error

Presence key: agent:{tenant_id}:{agent_id}:online  TTL 35s (heartbeat every 10s)
"""
import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent, AgentStatus
from app.models.assignment import Assignment
from app.models.conversation import Conversation, ConversationStatus

logger = logging.getLogger(__name__)

LOCK_TTL = 10  # seconds
PRESENCE_TTL = 35  # seconds


# ── Redis key builders ───────────────────────────────────────────────────────

def queue_key(tenant_id: str) -> str:
    return f"agents_queue:{tenant_id}"

def presence_key(tenant_id: str, agent_id: str) -> str:
    return f"agent:{tenant_id}:{agent_id}:online"

def lock_key(conversation_id: str) -> str:
    return f"lock:conversation:{conversation_id}"


# ── Presence ─────────────────────────────────────────────────────────────────

async def set_agent_online(redis: aioredis.Redis, tenant_id: str, agent_id: str) -> None:
    key = presence_key(tenant_id, agent_id)
    await redis.set(key, "1", ex=PRESENCE_TTL)
    # Ensure agent is in the round-robin queue (idempotent)
    q = queue_key(tenant_id)
    members = await redis.lrange(q, 0, -1)
    if agent_id not in members:
        await redis.rpush(q, agent_id)
    logger.debug("Agent %s ONLINE in tenant %s", agent_id, tenant_id)


async def set_agent_offline(redis: aioredis.Redis, tenant_id: str, agent_id: str) -> None:
    await redis.delete(presence_key(tenant_id, agent_id))
    logger.debug("Agent %s OFFLINE in tenant %s", agent_id, tenant_id)


async def refresh_presence(redis: aioredis.Redis, tenant_id: str, agent_id: str) -> None:
    """Called by heartbeat every 10s."""
    await redis.expire(presence_key(tenant_id, agent_id), PRESENCE_TTL)


async def is_online(redis: aioredis.Redis, tenant_id: str, agent_id: str) -> bool:
    return bool(await redis.exists(presence_key(tenant_id, agent_id)))


# ── Assignment ────────────────────────────────────────────────────────────────

async def assign_agent(
    redis: aioredis.Redis,
    db: AsyncSession,
    tenant_id: str,
    conversation_id: uuid.UUID,
) -> Agent | None:
    """
    Find best available agent and assign conversation.
    Assignment does NOT require the agent to be online —
    any active agent with capacity will do.
    Returns the Agent or None if none available.
    """
    conv_id_str = str(conversation_id)
    lock = lock_key(conv_id_str)

    # 1. Acquire distributed lock
    acquired = await redis.set(lock, "1", nx=True, ex=LOCK_TTL)
    if not acquired:
        logger.warning("Could not acquire lock for conversation %s", conv_id_str)
        return None

    try:
        q = queue_key(tenant_id)

        # If queue is empty, populate from DB so newly created agents are reachable
        queue_len = await redis.llen(q)
        if queue_len == 0:
            agents_result = await db.execute(
                select(Agent.id).where(Agent.active == True)
            )
            agent_ids = [str(row[0]) for row in agents_result.all()]
            if agent_ids:
                await redis.rpush(q, *agent_ids)
                queue_len = len(agent_ids)
                logger.info("Populated agent queue for tenant %s with %d agents", tenant_id, queue_len)

        if queue_len == 0:
            logger.info("No agents configured for tenant %s", tenant_id)
            return None

        # 2. Rotate through agents until we find one with capacity
        for _ in range(queue_len):
            agent_id = await redis.rpoplpush(q, q)
            if not agent_id:
                break

            # 3. Check DB capacity (no online/presence check — assign regardless)
            agent_uuid = uuid.UUID(agent_id)
            result = await db.execute(
                select(Agent).where(
                    Agent.id == agent_uuid,
                    Agent.active == True,
                )
            )
            agent = result.scalar_one_or_none()
            if not agent:
                continue

            active_count_result = await db.execute(
                select(func.count()).select_from(Conversation).where(
                    Conversation.assigned_agent_id == agent_uuid,
                    Conversation.status == ConversationStatus.HUMAN_ACTIVE,
                )
            )
            active_count = active_count_result.scalar_one()
            if active_count >= agent.max_concurrent_chats:
                continue

            # 4. Assign in DB transaction
            now = datetime.now(timezone.utc)
            await db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(
                    assigned_agent_id=agent.id,
                    status=ConversationStatus.HUMAN_ACTIVE,
                    updated_at=now,
                )
            )
            db.add(Assignment(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                agent_id=agent.id,
                assigned_at=now,
            ))
            await db.execute(
                update(Agent)
                .where(Agent.id == agent.id)
                .values(last_assigned_at=now)
            )
            await db.commit()
            logger.info("Assigned agent %s to conversation %s", agent_id, conv_id_str)
            return agent

        logger.info("No available agent found for tenant %s", tenant_id)
        return None

    finally:
        await redis.delete(lock)
