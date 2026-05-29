"""
Worker 1 — Message Ingestion

Consumes from  : messages_stream  (global)
Publishes to   : ai_processing_stream  (global)
                 (or human_assign_stream if conversation already has human assigned)

Responsibilities:
  1. Parse raw stream entry (tenant_id, conversation_id, message_id, external_id)
  2. Validate deduplication (external_id already in DB → skip with ACK)
  3. Upsert Conversation (NEW → BOT_ACTIVE on first message)
  4. Insert Message record
  5. Route to correct downstream stream
"""
import asyncio
import base64
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import AsyncSessionLocal, make_tenant_session
from app.db.tenant import set_tenant_schema
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageStatus, SenderType
from app.models.tenant import Tenant
from app.services.whatsapp import download_media
from app.services.message_stats import record_messages
from app.redis.client import get_redis
from app.redis.streams import (
    MESSAGES_STREAM,
    AI_STREAM,
    HUMAN_ASSIGN_STREAM,
    MSG_CONSUMER_GROUP,
    ensure_consumer_group,
    xadd,
    xreadgroup,
    xack,
    xautoclaim,
)
from app.websocket.manager import manager

logger = logging.getLogger(__name__)
import os
CONSUMER_NAME = f"ingest-{os.environ.get('HOSTNAME', '1')}"
BATCH = 10
BLOCK_MS = 2000
AUTOCLAIM_IDLE_MS = 30_000


async def _process_entry(redis, entry_id: str, data: dict) -> None:
    tenant_id = data.get("tenant_id")
    conversation_id = uuid.UUID(data["conversation_id"])
    external_id = data.get("external_id", "")
    phone = str(data.get("phone", ""))
    content = data.get("content", "")
    message_type = data.get("message_type", "text")
    media_id = data.get("media_id", "")

    schema = f"t_{data['tenant_slug']}"
    set_tenant_schema(schema)

    async with make_tenant_session(schema) as db:
        await db.execute(
            __import__("sqlalchemy", fromlist=["text"]).text(
                f"SET search_path TO {schema}, public"
            )
        )

        # 1. Deduplication
        if external_id:
            dup = await db.scalar(
                select(Message.id).where(Message.external_id == external_id)
            )
            if dup:
                logger.info("Duplicate message %s — skipping", external_id)
                return  # ACK happens in caller

        # 2. Upsert conversation
        conv = await db.scalar(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        now = datetime.now(timezone.utc)
        if conv is None:
            conv = Conversation(
                id=conversation_id,
                tenant_id=uuid.UUID(tenant_id),
                phone=phone,
                status=ConversationStatus.BOT_ACTIVE,
                created_at=now,
                updated_at=now,
                last_user_message_at=now,
            )
            db.add(conv)
            await db.flush()
        else:
            # Reopen closed conversations so the bot can respond again
            new_values: dict = {"updated_at": now, "last_user_message_at": now}
            if conv.status == ConversationStatus.CLOSED:
                new_values["status"] = ConversationStatus.BOT_ACTIVE
                new_values["assigned_agent_id"] = None
                new_values["closed_at"] = None
                logger.info("Reopening closed conv %s → BOT_ACTIVE", conversation_id)
            await db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(**new_values)
            )
            # Refresh to get updated status for routing below
            await db.refresh(conv)

        # 3. Insert message — download media if present
        media_content: str | None = None
        media_mime_type: str | None = None

        if media_id:
            try:
                # Load tenant token to authenticate against Meta API
                tenant = await db.scalar(
                    select(Tenant).where(Tenant.id == uuid.UUID(tenant_id))
                )
                if tenant and tenant.whatsapp_token:
                    raw_bytes, mime = await download_media(media_id, tenant.whatsapp_token)
                    media_content = base64.b64encode(raw_bytes).decode("ascii")
                    media_mime_type = mime
                    logger.info(
                        "Downloaded media %s (%s, %d bytes) for conv %s",
                        media_id, mime, len(raw_bytes), conversation_id,
                    )
                else:
                    logger.warning("No whatsapp_token for tenant %s — media not downloaded", tenant_id)
            except Exception as exc:
                logger.error("Failed to download media %s: %s", media_id, exc)

        msg = Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            external_id=external_id or None,
            sender_type=SenderType.USER,
            content=content,
            message_type=message_type,
            media_content=media_content,
            media_mime_type=media_mime_type,
            status=MessageStatus.PROCESSING,
            created_at=now,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(conv)

        # If the incoming message is an image, push its ID to the FIFO queue
        # so multiple images are processed in arrival order.
        PENDING_IMAGE_TTL = 3600  # 1 hour
        if message_type == "image":
            queue_key = f"pending_images:{conversation_id}"
            await redis.rpush(queue_key, str(msg.id))
            await redis.expire(queue_key, PENDING_IMAGE_TTL)
            logger.info("Queued pending image %s for conv %s", msg.id, conversation_id)

        # Notify agents via WebSocket so the UI updates in real time
        await manager.publish(data["tenant_slug"], {
            "type": "new_message",
            "conversation_id": str(conversation_id),
            "message": {
                "id": str(msg.id),
                "content": content,
                "sender_type": SenderType.USER.value,
                "message_type": message_type,
                "media_content": media_content,
                "media_mime_type": media_mime_type,
                "created_at": now.isoformat(),
            },
        })

        # 4. Route
        # HUMAN_ACTIVE (with agent) → notify agent stream
        # WAITING_HUMAN (no agent yet) → assignment stream to find one
        # Otherwise (BOT_ACTIVE / NEW) → AI stream
        if conv.status == ConversationStatus.HUMAN_ACTIVE and conv.assigned_agent_id:
            target_stream = HUMAN_ASSIGN_STREAM
        elif conv.status == ConversationStatus.WAITING_HUMAN:
            target_stream = HUMAN_ASSIGN_STREAM
        else:
            target_stream = AI_STREAM
        payload = {
            "tenant_id": tenant_id,
            "tenant_slug": data["tenant_slug"],
            "conversation_id": str(conversation_id),
            "message_id": str(msg.id),
            "phone": phone,
            "content": content,
            "message_type": message_type,
        }
        if conv.assigned_agent_id:
            payload["agent_id"] = str(conv.assigned_agent_id)

        await xadd(redis, target_stream, payload)
        logger.info(
            "Ingested msg %s → %s (conv %s)", msg.id, target_stream, conversation_id
        )

        # Accumulate user message counter
        try:
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as stats_db:
                await record_messages(uuid.UUID(tenant_id), stats_db, user=1)
        except Exception:
            logger.warning("Failed to record user message stat for tenant %s", tenant_id)


async def run(stop_event: asyncio.Event) -> None:
    redis = await get_redis()
    await ensure_consumer_group(redis, MESSAGES_STREAM, MSG_CONSUMER_GROUP)
    logger.info("message_ingestion worker started")

    while not stop_event.is_set():
        try:
            # Autoclaim stuck messages first
            stuck = await xautoclaim(
                redis, MESSAGES_STREAM, MSG_CONSUMER_GROUP,
                CONSUMER_NAME, AUTOCLAIM_IDLE_MS, count=5,
            )
            for entry_id, data in stuck:
                try:
                    await _process_entry(redis, entry_id, data)
                    await xack(redis, MESSAGES_STREAM, MSG_CONSUMER_GROUP, entry_id)
                except Exception:
                    logger.exception("Error reprocessing stuck entry %s", entry_id)

            # Normal read
            entries = await xreadgroup(
                redis, MSG_CONSUMER_GROUP, CONSUMER_NAME,
                MESSAGES_STREAM, count=BATCH, block=BLOCK_MS,
            )
            for entry_id, data in entries:
                try:
                    await _process_entry(redis, entry_id, data)
                    await xack(redis, MESSAGES_STREAM, MSG_CONSUMER_GROUP, entry_id)
                except Exception:
                    logger.exception("Error ingesting entry %s", entry_id)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("message_ingestion loop error")
            await asyncio.sleep(2)

    await redis.aclose()
    logger.info("message_ingestion worker stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    stop = asyncio.Event()
    asyncio.run(run(stop))
