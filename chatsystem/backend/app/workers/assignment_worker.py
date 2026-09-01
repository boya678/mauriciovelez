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
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal, make_tenant_session
from app.db.tenant import set_tenant_schema
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageStatus, SenderType
from app.models.tenant import Tenant
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
from app.services.handoff_lock import acquire_handoff_lock, release_handoff_lock
from app.services.whatsapp import send_text_message
from app.websocket.manager import manager

logger = logging.getLogger(__name__)
import os
CONSUMER_NAME = f"assign-{os.environ.get('HOSTNAME', '1')}"
BATCH = 10
BLOCK_MS = 3000
AUTOCLAIM_IDLE_MS = 45_000
RESCUE_INTERVAL_S = 30  # seconds between proactive scans for WAITING_HUMAN


def _window_open(last_user_message_at: datetime | None) -> bool:
    if last_user_message_at is None:
        return False
    if last_user_message_at.tzinfo is None:
        last_user_message_at = last_user_message_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last_user_message_at < timedelta(hours=24)


async def _ensure_handoff_notice(
    db: AsyncSession,
    tenant_id: str | uuid.UUID,
    tenant_slug: str,
    conv: Conversation,
) -> bool:
    if not _window_open(conv.last_user_message_at):
        logger.warning(
            "Cannot rescue conv %s: WhatsApp 24-hour window is closed",
            conv.id,
        )
        return False
    if conv.handoff_notice_sent_at is not None:
        return True

    async with AsyncSessionLocal() as public_db:
        tenant = await public_db.scalar(
            select(Tenant).where(Tenant.id == uuid.UUID(str(tenant_id)))
        )
    if not tenant or not tenant.whatsapp_phone_id or not tenant.whatsapp_token:
        logger.error("Cannot notify user before assigning conv %s: tenant credentials missing", conv.id)
        return False

    try:
        await send_text_message(
            phone_id=tenant.whatsapp_phone_id,
            token=tenant.whatsapp_token,
            to=conv.phone,
            text=settings.HUMAN_HANDOFF_NOTICE_TEXT,
        )
    except Exception:
        logger.exception("Cannot notify user before assigning conv %s", conv.id)
        return False

    now = datetime.now(timezone.utc)
    message = Message(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        sender_type=SenderType.BOT,
        content=settings.HUMAN_HANDOFF_NOTICE_TEXT,
        message_type="text",
        status=MessageStatus.PROCESSED,
        created_at=now,
    )
    db.add(message)
    conv.handoff_notice_sent_at = now
    conv.last_activity_at = now
    conv.idle_warning_sent_at = None
    conv.updated_at = now
    await db.commit()
    await manager.publish(tenant_slug, {
        "type": "new_message",
        "conversation_id": str(conv.id),
        "message": {
            "id": str(message.id),
            "content": message.content,
            "sender_type": SenderType.BOT.value,
            "message_type": "text",
            "created_at": now.isoformat(),
        },
    })
    logger.info("Delivered missing handoff notice for conv %s", conv.id)
    return True


async def _process_entry(redis, entry_id: str, data: dict) -> bool:
    conversation_id = uuid.UUID(data["conversation_id"])
    lock_token = await acquire_handoff_lock(redis, conversation_id)
    if lock_token is None:
        return False

    try:
        return await _process_entry_locked(redis, entry_id, data)
    finally:
        await release_handoff_lock(redis, conversation_id, lock_token)


async def _process_entry_locked(redis, entry_id: str, data: dict) -> bool:
    """Returns True if processed (should ACK), False if should retry."""
    tenant_id = data["tenant_id"]
    tenant_slug = data["tenant_slug"]
    conversation_id = uuid.UUID(data["conversation_id"])

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

        if not _window_open(conv.last_user_message_at):
            logger.warning(
                "Not retrying assignment for conv %s: WhatsApp 24-hour window is closed",
                conversation_id,
            )
            return True

        if not await _ensure_handoff_notice(db, tenant_id, tenant_slug, conv):
            return False

        # _ensure_handoff_notice may commit a newly delivered legacy notice,
        # which releases the row lock. Reacquire it and re-check ownership.
        conv = await db.scalar(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if conv is None or conv.status != ConversationStatus.WAITING_HUMAN:
            return True

        agent = await assign_agent(redis, db, tenant_slug, conversation_id)

        if agent is None:
            logger.info(
                "No agent available for conv %s; rescue scanner will retry",
                conversation_id,
            )
            return True

        # Notify the assigned agent via WebSocket (keyed by slug, matches WS path)
        await manager.publish(tenant_slug, {
            "type": "conversation_assigned",
            "conversation_id": str(conversation_id),
            "agent_id": str(agent.id),
            "phone": data.get("phone", ""),
        })
        logger.info("Assigned conv %s to agent %s", conversation_id, agent.id)
        return True


async def _rescue_waiting_conversations(redis) -> None:
    """
    Proactive scanner: finds all WAITING_HUMAN conversations across every
    active tenant and tries to assign them to an available agent.
    Runs every RESCUE_INTERVAL_S seconds so conversations are picked up when
    agent capacity becomes available.
    """
    async with AsyncSessionLocal() as pub_db:
        result = await pub_db.execute(
            select(Tenant.slug, Tenant.id).where(Tenant.active == True)
        )
        tenants = result.all()

    for slug, tenant_id in tenants:
        schema = f"t_{slug}"
        set_tenant_schema(schema)
        try:
            async with make_tenant_session(schema) as db:
                await db.execute(text(f"SET search_path TO {schema}, public"))
                waiting_result = await db.execute(
                    select(Conversation.id, Conversation.phone)
                    .where(
                        Conversation.status == ConversationStatus.WAITING_HUMAN,
                        Conversation.last_user_message_at.is_not(None),
                        Conversation.last_user_message_at >= (
                            datetime.now(timezone.utc) - timedelta(hours=24)
                        ),
                    )
                    .order_by(Conversation.updated_at.asc())  # FIFO: oldest waiting first
                )
                waiting = waiting_result.all()

            for conv_id, phone in waiting:
                lock_token = await acquire_handoff_lock(redis, conv_id)
                if lock_token is None:
                    continue
                try:
                    async with make_tenant_session(schema) as db:
                        await db.execute(text(f"SET search_path TO {schema}, public"))
                        # Re-check status — may have been assigned between queries
                        conv = await db.scalar(
                            select(Conversation).where(Conversation.id == conv_id)
                        )
                        if conv is None or conv.status != ConversationStatus.WAITING_HUMAN:
                            continue

                        if not await _ensure_handoff_notice(db, tenant_id, slug, conv):
                            continue

                        conv = await db.scalar(
                            select(Conversation)
                            .where(Conversation.id == conv_id)
                            .execution_options(populate_existing=True)
                            .with_for_update()
                        )
                        if conv is None or conv.status != ConversationStatus.WAITING_HUMAN:
                            continue

                        agent = await assign_agent(redis, db, slug, conv_id)
                        if agent is not None:
                            await manager.publish(slug, {
                                "type": "conversation_assigned",
                                "conversation_id": str(conv_id),
                                "agent_id": str(agent.id),
                                "phone": phone,
                            })
                            logger.info(
                                "Rescue: assigned conv %s → agent %s (tenant %s)",
                                conv_id, agent.id, slug,
                            )
                finally:
                    await release_handoff_lock(redis, conv_id, lock_token)
        except Exception:
            logger.exception("Rescue scanner error for tenant %s", slug)


async def _rescue_loop(redis, stop_event: asyncio.Event) -> None:
    """Background task that periodically calls the rescue scanner."""
    while not stop_event.is_set():
        await asyncio.sleep(RESCUE_INTERVAL_S)
        if stop_event.is_set():
            break
        try:
            await _rescue_waiting_conversations(redis)
        except Exception:
            logger.exception("Rescue loop error")


async def run(stop_event: asyncio.Event) -> None:
    redis = await get_redis()
    manager.set_redis(redis)
    await ensure_consumer_group(redis, HUMAN_ASSIGN_STREAM, ASSIGN_CONSUMER_GROUP)
    logger.info("assignment_worker started")

    rescue_task = asyncio.create_task(_rescue_loop(redis, stop_event))

    while not stop_event.is_set():
        try:
            stuck = await xautoclaim(
                redis, HUMAN_ASSIGN_STREAM, ASSIGN_CONSUMER_GROUP,
                CONSUMER_NAME, AUTOCLAIM_IDLE_MS, count=10,
            )
            for entry_id, data in stuck:
                try:
                    ok = await _process_entry(redis, entry_id, data)
                    if ok:
                        await xack(redis, HUMAN_ASSIGN_STREAM, ASSIGN_CONSUMER_GROUP, entry_id)
                except Exception:
                    logger.exception("Error in stuck assign entry %s", entry_id)

            entries = await xreadgroup(
                redis, ASSIGN_CONSUMER_GROUP, CONSUMER_NAME,
                HUMAN_ASSIGN_STREAM, count=BATCH, block=BLOCK_MS,
            )
            for entry_id, data in entries:
                try:
                    ok = await _process_entry(redis, entry_id, data)
                    if ok:
                        await xack(redis, HUMAN_ASSIGN_STREAM, ASSIGN_CONSUMER_GROUP, entry_id)
                except Exception:
                    logger.exception("Error in assign entry %s", entry_id)

        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("assignment_worker loop error")
            await asyncio.sleep(2)

    rescue_task.cancel()
    try:
        await rescue_task
    except asyncio.CancelledError:
        pass

    await redis.aclose()
    logger.info("assignment_worker stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    stop = asyncio.Event()
    asyncio.run(run(stop))
