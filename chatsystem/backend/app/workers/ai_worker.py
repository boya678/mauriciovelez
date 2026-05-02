"""
Worker 2 — AI Worker

Consumes from  : ai_processing_stream
Publishes to   : outgoing_stream        (bot reply → WhatsApp)
                 human_assign_stream    (escalation → round-robin)

Responsibilities:
  1. Load full conversation history from DB
  2. Run LangGraph (classifier + specialist node)
  3. If bot reply → insert bot Message + publish to outgoing_stream
  4. If escalation → update conversation status to WAITING_HUMAN
                    + publish to human_assign_stream
  5. Publish WebSocket event to notify agents
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.agents.graph import run_graph
from app.db.session import AsyncSessionLocal, make_tenant_session
from app.db.tenant import set_tenant_schema
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageStatus, SenderType
from app.models.tenant import Tenant
from app.redis.client import get_redis
from app.redis.streams import (
    AI_STREAM,
    AI_CONSUMER_GROUP,
    HUMAN_ASSIGN_STREAM,
    OUTGOING_STREAM,
    ensure_consumer_group,
    xadd,
    xreadgroup,
    xack,
    xautoclaim,
)
from app.services.tool_engine import load_tools
from app.websocket.manager import manager

logger = logging.getLogger(__name__)
CONSUMER_NAME = "ai-1"
BATCH = 5
BLOCK_MS = 2000
AUTOCLAIM_IDLE_MS = 60_000  # AI calls can be slow


async def _load_history(db, conversation_id: uuid.UUID) -> list[dict]:
    msgs = await db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    history = []
    for m in msgs.all():
        role = "user" if m.sender_type == SenderType.USER else "bot"
        history.append({"role": role, "content": m.content})
    return history


async def _process_entry(redis, entry_id: str, data: dict) -> None:
    tenant_id = data["tenant_id"]
    tenant_slug = data["tenant_slug"]
    conversation_id = uuid.UUID(data["conversation_id"])
    message_id = uuid.UUID(data["message_id"])
    phone = data["phone"]

    schema = f"t_{tenant_slug}"
    set_tenant_schema(schema)

    async with make_tenant_session(schema) as db:
        from sqlalchemy import text
        await db.execute(text(f"SET search_path TO {schema}, public"))

        # Load tenant system prompt
        tenant = await db.scalar(
            select(Tenant).where(Tenant.id == uuid.UUID(tenant_id))
        )
        system_prompt = tenant.ai_system_prompt if tenant else ""

        # Load conversation + message count for turn tracking
        conv = await db.scalar(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        if conv is None or conv.status not in (
            ConversationStatus.BOT_ACTIVE, ConversationStatus.NEW
        ):
            logger.info("Conv %s not in BOT_ACTIVE state, skipping AI", conversation_id)
            return

        history = await _load_history(db, conversation_id)
        bot_turns = sum(1 for m in history if m["role"] == "bot")

        # Load dynamic tools for this tenant
        tools = await load_tools(
            db=db,
            tenant_id=uuid.UUID(tenant_id),
            phone=phone,
            conversation_id=str(conversation_id),
            tenant_slug=tenant_slug,
        )

        now = datetime.now(timezone.utc)

        # Run LangGraph
        result = await run_graph(
            messages=history,
            tenant_system_prompt=system_prompt,
            turns=bot_turns,
            tools=tools,
        )

        if result["needs_escalation"]:
            # Send a goodbye bot message first if there is a reply
            if result["bot_reply"]:
                farewell = Message(
                    id=uuid.uuid4(),
                    conversation_id=conversation_id,
                    sender_type=SenderType.BOT,
                    content=result["bot_reply"],
                    status=MessageStatus.PROCESSED,
                    created_at=now,
                )
                db.add(farewell)
                await xadd(redis, OUTGOING_STREAM, {
                    "tenant_id": tenant_id,
                    "tenant_slug": tenant_slug,
                    "phone": phone,
                    "message_id": str(farewell.id),
                    "content": result["bot_reply"],
                    "phone_id": tenant.whatsapp_phone_id if tenant else "",
                    "token": tenant.whatsapp_token if tenant else "",
                })

            # Update conversation status
            await db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(status=ConversationStatus.WAITING_HUMAN, updated_at=now)
            )
            await db.commit()

            await xadd(redis, HUMAN_ASSIGN_STREAM, {
                "tenant_id": tenant_id,
                "tenant_slug": tenant_slug,
                "conversation_id": str(conversation_id),
                "phone": phone,
            })

            # Notify agents via WebSocket
            await manager.publish(tenant_slug, {
                "type": "conversation_waiting",
                "conversation_id": str(conversation_id),
                "phone": phone,
            })
            logger.info("Escalated conv %s → WAITING_HUMAN", conversation_id)

        else:
            # Bot reply
            bot_msg = Message(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                sender_type=SenderType.BOT,
                content=result["bot_reply"],
                status=MessageStatus.PROCESSED,
                created_at=now,
            )
            db.add(bot_msg)
            await db.execute(
                update(Message)
                .where(Message.id == message_id)
                .values(status=MessageStatus.PROCESSED)
            )
            await db.commit()

            await xadd(redis, OUTGOING_STREAM, {
                "tenant_id": tenant_id,
                "tenant_slug": tenant_slug,
                "phone": phone,
                "message_id": str(bot_msg.id),
                "content": result["bot_reply"],
                "phone_id": tenant.whatsapp_phone_id if tenant else "",
                "token": tenant.whatsapp_token if tenant else "",
            })
            logger.info("Bot replied to conv %s", conversation_id)


async def run(stop_event: asyncio.Event) -> None:
    redis = await get_redis()
    manager.set_redis(redis)
    await ensure_consumer_group(redis, AI_STREAM, AI_CONSUMER_GROUP)
    logger.info("ai_worker started")

    while not stop_event.is_set():
        try:
            stuck = await xautoclaim(
                redis, AI_STREAM, AI_CONSUMER_GROUP,
                CONSUMER_NAME, AUTOCLAIM_IDLE_MS, count=3,
            )
            for entry_id, data in stuck:
                try:
                    await _process_entry(redis, entry_id, data)
                    await xack(redis, AI_STREAM, AI_CONSUMER_GROUP, entry_id)
                except Exception:
                    logger.exception("Error reprocessing AI stuck entry %s", entry_id)

            entries = await xreadgroup(
                redis, AI_CONSUMER_GROUP, CONSUMER_NAME,
                AI_STREAM, count=BATCH, block=BLOCK_MS,
            )
            for entry_id, data in entries:
                try:
                    await _process_entry(redis, entry_id, data)
                    await xack(redis, AI_STREAM, AI_CONSUMER_GROUP, entry_id)
                except Exception:
                    logger.exception("Error in AI entry %s", entry_id)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("ai_worker loop error")
            await asyncio.sleep(2)

    await redis.aclose()
    logger.info("ai_worker stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    stop = asyncio.Event()
    asyncio.run(run(stop))
