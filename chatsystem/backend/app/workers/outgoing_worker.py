"""
Worker 4 — Outgoing Worker

Consumes from  : outgoing_stream
Side effects   : Sends message via WhatsApp Cloud API
                 Updates Message.status → PROCESSED | ERROR
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
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
from app.services.whatsapp import send_text_message, send_interactive_message, send_template_message

logger = logging.getLogger(__name__)
import os
CONSUMER_NAME = f"outgoing-{os.environ.get('HOSTNAME', '1')}"
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
    interactive_raw = data.get("interactive_payload", "")
    # Window flag: absent (bot replies) or "1" means open; "0" means expired → use template
    window_open = data.get("window_open", "1") != "0"
    template_name = data.get("template_name", "")
    template_language = data.get("template_language", "es") or "es"

    schema = f"t_{tenant_slug}" if tenant_slug else "public"

    print(f"[OUTGOING] sending msg={message_id} phone={phone} interactive={bool(interactive_raw)} template={template_name or '-'} window_open={window_open}", flush=True)

    try:
        if interactive_raw:
            interactive = json.loads(interactive_raw) if isinstance(interactive_raw, str) else interactive_raw
            await send_interactive_message(
                phone_id=phone_id,
                token=token,
                to=phone,
                interactive=interactive,
            )
        elif not window_open and template_name:
            # 24-hour window expired — must use a pre-approved template
            logger.info("Window expired for %s — sending template '%s'", phone, template_name)
            await send_template_message(
                phone_id=phone_id,
                token=token,
                to=phone,
                template_name=template_name,
                language=template_language,
            )
        else:
            await send_text_message(
                phone_id=phone_id,
                token=token,
                to=phone,
                text=content,
            )
        new_status = MessageStatus.PROCESSED
        print(f"[OUTGOING] OK msg={message_id} phone={phone}", flush=True)
    except httpx.HTTPStatusError as exc:
        body = exc.response.text if exc.response is not None else ""
        status_code = exc.response.status_code if exc.response is not None else "?"
        print(
            f"[OUTGOING] HTTP-ERROR msg={message_id} phone={phone} status={status_code} body={body}",
            flush=True,
        )
        logger.error(
            "WhatsApp send failed for msg %s phone=%s status=%s body=%s",
            message_id, phone, status_code, body,
        )
        new_status = MessageStatus.ERROR
    except Exception as exc:
        import traceback
        print(
            f"[OUTGOING] EXC msg={message_id} phone={phone} type={type(exc).__name__} err={exc}\n{traceback.format_exc()}",
            flush=True,
        )
        logger.exception("WhatsApp send failed for msg %s phone=%s", message_id, phone)
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
