"""
Worker 4 — Outgoing Worker

Consumes from  : outgoing_stream
Side effects   : Sends message via WhatsApp Cloud API
                 Updates Message.status → PROCESSED | ERROR
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import update, text

from app.db.session import AsyncSessionLocal, make_tenant_session
from app.models.message import Message, MessageStatus
from app.redis.client import get_redis
from app.redis.streams import (
    OUTGOING_STREAM,
    OUTGOING_CONSUMER_GROUP,
    ensure_consumer_group,
    xreadgroup,
    xack,
    xautoclaim,
)
from app.services.whatsapp import send_text_message

logger = logging.getLogger(__name__)
CONSUMER_NAME = "outgoing-1"
BATCH = 10
BLOCK_MS = 1000
AUTOCLAIM_IDLE_MS = 30_000


async def _process_entry(entry_id: str, data: dict) -> None:
    phone = str(data["phone"])
    content = str(data["content"])
    message_id = uuid.UUID(data["message_id"])
    phone_id = data.get("phone_id", "")
    token = data.get("token", "")
    tenant_slug = data.get("tenant_slug", "")

    schema = f"t_{tenant_slug}" if tenant_slug else "public"

    try:
        await send_text_message(
            phone_id=phone_id,
            token=token,
            to=phone,
            text=content,
        )
        new_status = MessageStatus.PROCESSED
    except Exception as exc:
        logger.error("WhatsApp send failed for msg %s: %s", message_id, exc)
        new_status = MessageStatus.ERROR

    async with make_tenant_session(schema) as db:
        await db.execute(text(f"SET search_path TO {schema}, public"))
        await db.execute(
            update(Message)
            .where(Message.id == message_id)
            .values(status=new_status)
        )
        await db.commit()

    logger.info("Outgoing msg %s → %s status=%s", message_id, phone, new_status.value)


async def run(stop_event: asyncio.Event) -> None:
    redis = await get_redis()
    await ensure_consumer_group(redis, OUTGOING_STREAM, OUTGOING_CONSUMER_GROUP)
    logger.info("outgoing_worker started")

    while not stop_event.is_set():
        try:
            stuck = await xautoclaim(
                redis, OUTGOING_STREAM, OUTGOING_CONSUMER_GROUP,
                CONSUMER_NAME, AUTOCLAIM_IDLE_MS, count=10,
            )
            for entry_id, data in stuck:
                try:
                    await _process_entry(entry_id, data)
                    await xack(redis, OUTGOING_STREAM, OUTGOING_CONSUMER_GROUP, entry_id)
                except Exception:
                    logger.exception("Error reprocessing outgoing entry %s", entry_id)

            entries = await xreadgroup(
                redis, OUTGOING_CONSUMER_GROUP, CONSUMER_NAME,
                OUTGOING_STREAM, count=BATCH, block=BLOCK_MS,
            )
            for entry_id, data in entries:
                try:
                    await _process_entry(entry_id, data)
                    await xack(redis, OUTGOING_STREAM, OUTGOING_CONSUMER_GROUP, entry_id)
                except Exception:
                    logger.exception("Error in outgoing entry %s", entry_id)

        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("outgoing_worker loop error")
            await asyncio.sleep(2)

    await redis.aclose()
    logger.info("outgoing_worker stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    stop = asyncio.Event()
    asyncio.run(run(stop))
