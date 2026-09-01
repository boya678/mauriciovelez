"""
Worker 4 — Outgoing Worker

Consumes from  : outgoing_stream
Side effects   : Sends message via WhatsApp Cloud API
                 Updates Message.status → PROCESSED | ERROR
"""
import asyncio
import base64
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select, update, text

from app.core.config import settings
from app.db.session import AsyncSessionLocal, make_tenant_session
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageStatus, SenderType
from app.redis.client import get_redis
from app.redis.streams import (
    HUMAN_ASSIGN_STREAM,
    OUTGOING_STREAM,
    OUTGOING_CONSUMER_GROUP,
    ensure_consumer_group,
    xadd,
    xreadgroup,
    xack,
    xautoclaim,
)
from app.services.handoff_lock import acquire_handoff_lock, release_handoff_lock
from app.services.whatsapp import (
    send_text_message,
    send_interactive_message,
    send_template_message,
    send_image_message,
    send_audio_message,
    upload_media,
)
from app.websocket.manager import manager

logger = logging.getLogger(__name__)
import os
CONSUMER_NAME = f"outgoing-{os.environ.get('HOSTNAME', '1')}"
BATCH = 10
BLOCK_MS = 1000
AUTOCLAIM_IDLE_MS = 30_000
RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def _retry_key(message_id: uuid.UUID) -> str:
    return f"outgoing_retry:{message_id}"


def _processing_lock_key(message_id: uuid.UUID) -> str:
    return f"outgoing_processing:{message_id}"


async def _can_retry(redis, message_id: uuid.UUID) -> bool:
    key = _retry_key(message_id)
    attempts = await redis.incr(key)
    await redis.expire(key, settings.OUTGOING_RETRY_TTL_SECONDS)
    return attempts < settings.OUTGOING_MAX_RETRIES


def _window_open(last_user_message_at: datetime | None) -> bool:
    if last_user_message_at is None:
        return False
    if last_user_message_at.tzinfo is None:
        last_user_message_at = last_user_message_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last_user_message_at < timedelta(hours=24)


async def _process_entry(redis, entry_id: str, data: dict) -> bool:
    message_id = uuid.UUID(data["message_id"])
    lock_key = _processing_lock_key(message_id)
    lock_token = str(uuid.uuid4())
    acquired = await redis.set(
        lock_key,
        lock_token,
        nx=True,
        ex=settings.OUTGOING_PROCESSING_LOCK_SECONDS,
    )
    if not acquired:
        logger.info("Outgoing msg %s is being processed by another worker", message_id)
        return False

    conversation_id: uuid.UUID | None = None
    conversation_lock_token: str | None = None
    try:
        tenant_slug = data.get("tenant_slug", "")
        schema = f"t_{tenant_slug}" if tenant_slug else "public"
        async with make_tenant_session(schema) as db:
            await db.execute(text(f"SET search_path TO {schema}, public"))
            queued_message = await db.scalar(
                select(Message).where(Message.id == message_id)
            )
        if (
            queued_message is not None
            and queued_message.status not in (MessageStatus.PROCESSED, MessageStatus.ERROR)
            and queued_message.sender_type == SenderType.BOT
        ):
            conversation_id = queued_message.conversation_id
            conversation_lock_token = await acquire_handoff_lock(
                redis, conversation_id
            )
            if conversation_lock_token is None:
                logger.info(
                    "Bot output for conv %s is blocked by another conversation action",
                    conversation_id,
                )
                return False
        return await _process_entry_locked(redis, entry_id, data)
    finally:
        if conversation_id is not None and conversation_lock_token is not None:
            await release_handoff_lock(
                redis, conversation_id, conversation_lock_token
            )
        await redis.eval(RELEASE_LOCK_SCRIPT, 1, lock_key, lock_token)


async def _process_entry_locked(redis, entry_id: str, data: dict) -> bool:
    phone = str(data["phone"])
    content = str(data["content"])
    message_id = uuid.UUID(data["message_id"])
    phone_id = data.get("phone_id", "")
    token = data.get("token", "")
    tenant_slug = data.get("tenant_slug", "")
    interactive_raw = data.get("interactive_payload", "")
    message_type = str(data.get("message_type", "text") or "text")
    media_content = data.get("media_content", "")
    media_mime_type = data.get("media_mime_type", "")
    media_filename = data.get("media_filename", "upload.bin")
    # Window flag: absent (bot replies) or "1" means open; "0" means expired → use template
    window_open = data.get("window_open", "1") != "0"
    template_name = data.get("template_name", "")
    template_language = data.get("template_language", "es") or "es"
    handoff_after_send = bool(data.get("handoff_after_send", False))
    conversation_id_raw = data.get("conversation_id", "")

    schema = f"t_{tenant_slug}" if tenant_slug else "public"

    async with make_tenant_session(schema) as db:
        await db.execute(text(f"SET search_path TO {schema}, public"))
        queued_message = await db.scalar(
            select(Message).where(Message.id == message_id)
        )
        if queued_message is None:
            logger.error("Outgoing msg %s does not exist; discarding stream entry", message_id)
            return True
        if queued_message.status in (MessageStatus.PROCESSED, MessageStatus.ERROR):
            logger.info(
                "Outgoing msg %s already terminal (%s); skipping redelivery",
                message_id,
                queued_message.status,
            )
            await redis.delete(_retry_key(message_id))
            return True

        if not conversation_id_raw:
            conversation_id_raw = str(queued_message.conversation_id)

        if conversation_id_raw:
            conversation_id = uuid.UUID(str(conversation_id_raw))
            conv = await db.scalar(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            cancel_reason = ""
            live_window_open = conv is not None and _window_open(conv.last_user_message_at)

            if conv is None:
                cancel_reason = "conversation no longer exists"
            elif handoff_after_send:
                if conv.status not in (
                    ConversationStatus.NEW,
                    ConversationStatus.BOT_ACTIVE,
                ):
                    cancel_reason = f"conversation status is {conv.status}"
                elif not live_window_open:
                    cancel_reason = "WhatsApp 24-hour window is closed"
            elif conv.status == ConversationStatus.CLOSED:
                cancel_reason = "conversation is closed"
            elif (
                queued_message.sender_type == SenderType.BOT
                and conv.status not in (
                    ConversationStatus.NEW,
                    ConversationStatus.BOT_ACTIVE,
                )
            ):
                cancel_reason = f"bot no longer owns conversation ({conv.status})"
            elif not live_window_open:
                can_use_template = (
                    bool(template_name)
                    and not interactive_raw
                    and message_type == "text"
                    and not media_content
                )
                if can_use_template:
                    window_open = False
                else:
                    cancel_reason = "WhatsApp 24-hour window is closed"

            if cancel_reason:
                await db.execute(
                    update(Message)
                    .where(Message.id == message_id)
                    .values(status=MessageStatus.ERROR)
                )
                await db.commit()
                logger.warning(
                    "Outgoing msg %s cancelled for conv %s: %s",
                    message_id,
                    conversation_id,
                    cancel_reason,
                )
                await redis.delete(_retry_key(message_id))
                return True

    print(
        f"[OUTGOING] sending msg={message_id} phone={phone} type={message_type} "
        f"interactive={bool(interactive_raw)} template={template_name or '-'} window_open={window_open}",
        flush=True,
    )

    # Default to PROCESSED for all success paths. Branches that succeed without
    # explicitly setting new_status (interactive / image / audio / template)
    # would otherwise leave the variable unbound when the DB UPDATE runs.
    new_status: MessageStatus = MessageStatus.PROCESSED
    should_retry = False

    try:
        if interactive_raw:
            interactive = json.loads(interactive_raw) if isinstance(interactive_raw, str) else interactive_raw
            await send_interactive_message(
                phone_id=phone_id,
                token=token,
                to=phone,
                interactive=interactive,
            )
        elif message_type == "image" and media_content:
            media_bytes = base64.b64decode(media_content)
            mime = str(media_mime_type or "image/jpeg")
            filename = str(media_filename or "image.jpg")
            media_id = await upload_media(phone_id, token, media_bytes, mime, filename)
            await send_image_message(
                phone_id=phone_id,
                token=token,
                to=phone,
                media_id=media_id,
                caption=content if content and content != "[imagen]" else None,
            )
        elif message_type == "audio" and media_content:
            media_bytes = base64.b64decode(media_content)
            mime = str(media_mime_type or "audio/ogg")
            filename = str(media_filename or "audio.ogg")
            # WhatsApp does not support audio/webm or video/webm.
            # Convert to ogg/opus before uploading.
            if "webm" in mime:
                try:
                    import io as _io
                    from pydub import AudioSegment as _AS
                    _audio = _AS.from_file(_io.BytesIO(media_bytes), format="webm")
                    _buf = _io.BytesIO()
                    _audio.export(_buf, format="ogg", codec="libopus")
                    media_bytes = _buf.getvalue()
                    mime = "audio/ogg"
                    filename = (filename.rsplit(".", 1)[0] if "." in filename else filename) + ".ogg"
                    logger.info("Converted webm audio to ogg for msg %s", message_id)
                except Exception as _conv_err:
                    logger.warning("Audio webm→ogg conversion failed for msg %s: %s", message_id, _conv_err)
            media_id = await upload_media(phone_id, token, media_bytes, mime, filename)
            await send_audio_message(
                phone_id=phone_id,
                token=token,
                to=phone,
                media_id=media_id,
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
            if not content or not content.strip():
                # Nothing to send (LLM returned empty content, e.g. reasoning
                # model ran out of tokens). Mark processed and skip to avoid
                # WhatsApp 400 "text.body is required".
                logger.warning(
                    "Empty content for msg %s phone=%s \u2192 skipping send",
                    message_id, phone,
                )
                new_status = MessageStatus.PROCESSED
                print(f"[OUTGOING] SKIP-EMPTY msg={message_id} phone={phone}", flush=True)
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
        transient = isinstance(status_code, int) and (
            status_code == 429 or status_code >= 500
        )
        should_retry = transient and await _can_retry(redis, message_id)
        new_status = MessageStatus.PENDING if should_retry else MessageStatus.ERROR
    except Exception as exc:
        import traceback
        print(
            f"[OUTGOING] EXC msg={message_id} phone={phone} type={type(exc).__name__} err={exc}\n{traceback.format_exc()}",
            flush=True,
        )
        logger.exception("WhatsApp send failed for msg %s phone=%s", message_id, phone)
        should_retry = await _can_retry(redis, message_id)
        new_status = MessageStatus.PENDING if should_retry else MessageStatus.ERROR

    handoff_ready = False
    conversation_id: uuid.UUID | None = None
    async with make_tenant_session(schema) as db:
        await db.execute(text(f"SET search_path TO {schema}, public"))
        await db.execute(
            update(Message)
            .where(Message.id == message_id)
            .values(status=new_status)
        )

        if new_status == MessageStatus.PROCESSED:
            message = await db.scalar(select(Message).where(Message.id == message_id))
            if message:
                await db.execute(
                    update(Conversation)
                    .where(Conversation.id == message.conversation_id)
                    .values(
                        last_activity_at=datetime.now(timezone.utc),
                        idle_warning_sent_at=None,
                    )
                )

        if handoff_after_send and new_status == MessageStatus.PROCESSED and conversation_id_raw:
            conversation_id = uuid.UUID(str(conversation_id_raw))
            conv = await db.scalar(
                select(Conversation)
                .where(Conversation.id == conversation_id)
                .with_for_update()
            )
            if conv and conv.status in (
                ConversationStatus.NEW,
                ConversationStatus.BOT_ACTIVE,
            ) and conv.handoff_notice_sent_at is None:
                now = datetime.now(timezone.utc)
                conv.status = ConversationStatus.WAITING_HUMAN
                conv.updated_at = now
                conv.handoff_notice_sent_at = now
                handoff_ready = True
        await db.commit()

    if handoff_ready and conversation_id is not None:
        await xadd(redis, HUMAN_ASSIGN_STREAM, {
            "tenant_id": data.get("tenant_id", ""),
            "tenant_slug": tenant_slug,
            "conversation_id": str(conversation_id),
            "phone": phone,
        })
        await manager.publish(tenant_slug, {
            "type": "conversation_waiting",
            "conversation_id": str(conversation_id),
            "phone": phone,
        })
        logger.info("Handoff notice delivered; conv %s → WAITING_HUMAN", conversation_id)
    elif handoff_after_send and new_status == MessageStatus.ERROR:
        logger.error(
            "Handoff cancelled for conv %s because its notice could not be delivered",
            conversation_id_raw,
        )

    if new_status == MessageStatus.PROCESSED or not should_retry:
        await redis.delete(_retry_key(message_id))

    logger.info("Outgoing msg %s → %s status=%s", message_id, phone, new_status.value)
    return not should_retry


async def run(stop_event: asyncio.Event) -> None:
    redis = await get_redis()
    manager.set_redis(redis)
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
                    completed = await _process_entry(redis, entry_id, data)
                    if completed:
                        await xack(redis, OUTGOING_STREAM, OUTGOING_CONSUMER_GROUP, entry_id)
                except Exception:
                    logger.exception("Error reprocessing outgoing entry %s", entry_id)

            entries = await xreadgroup(
                redis, OUTGOING_CONSUMER_GROUP, CONSUMER_NAME,
                OUTGOING_STREAM, count=BATCH, block=BLOCK_MS,
            )
            for entry_id, data in entries:
                try:
                    completed = await _process_entry(redis, entry_id, data)
                    if completed:
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
