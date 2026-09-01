"""Warn users and close conversations that are waiting for their reply."""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, or_, select, update

from app.core.config import settings
from app.db.session import AsyncSessionLocal, make_tenant_session
from app.db.tenant import set_tenant_schema
from app.models.assignment import Assignment
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageStatus, SenderType
from app.models.tenant import Tenant
from app.redis.client import get_redis
from app.services.handoff_lock import acquire_handoff_lock, release_handoff_lock
from app.services.whatsapp import send_text_message
from app.websocket.manager import manager

logger = logging.getLogger(__name__)

SCAN_LOCK = "conversation_lifecycle:scan"
RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def _window_open(
    last_user_message_at: datetime | None,
    required_minutes: int = 0,
) -> bool:
    if last_user_message_at is None:
        return False
    if last_user_message_at.tzinfo is None:
        last_user_message_at = last_user_message_at.replace(tzinfo=timezone.utc)
    deadline = last_user_message_at + timedelta(hours=24)
    return datetime.now(timezone.utc) + timedelta(minutes=required_minutes) < deadline


def _warning_text() -> str:
    return settings.CONVERSATION_IDLE_WARNING_TEXT.replace(
        "{minutes}", str(settings.CONVERSATION_IDLE_GRACE_MINUTES)
    )


async def _latest_message(db, conversation_id: uuid.UUID) -> Message | None:
    return await db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(desc(Message.created_at))
        .limit(1)
    )


def _is_waiting_for_user(conv: Conversation, latest: Message | None) -> bool:
    if latest is None or latest.status != MessageStatus.PROCESSED:
        return False
    if conv.status == ConversationStatus.BOT_ACTIVE:
        return latest.sender_type == SenderType.BOT
    if conv.status == ConversationStatus.HUMAN_ACTIVE:
        return latest.sender_type == SenderType.HUMAN
    return False


async def _publish_message(
    tenant_slug: str,
    conversation_id: uuid.UUID,
    message: Message,
) -> None:
    await manager.publish(tenant_slug, {
        "type": "new_message",
        "conversation_id": str(conversation_id),
        "message": {
            "id": str(message.id),
            "content": message.content,
            "sender_type": SenderType.BOT.value,
            "message_type": "text",
            "created_at": message.created_at.isoformat(),
        },
    })


async def _warn_conversation(tenant: Tenant, conv_id: uuid.UUID, cutoff: datetime) -> None:
    schema = f"t_{tenant.slug}"
    set_tenant_schema(schema)
    async with make_tenant_session(schema) as db:
        conv = await db.scalar(
            select(Conversation)
            .where(Conversation.id == conv_id)
            .with_for_update()
        )
        if (
            conv is None
            or conv.idle_warning_sent_at is not None
            or conv.last_activity_at is None
            or conv.last_activity_at > cutoff
            or not _window_open(
                conv.last_user_message_at,
                settings.CONVERSATION_IDLE_GRACE_MINUTES,
            )
        ):
            return

        latest = await _latest_message(db, conv.id)
        if not _is_waiting_for_user(conv, latest):
            return

        text = _warning_text()
        await send_text_message(
            phone_id=tenant.whatsapp_phone_id or "",
            token=tenant.whatsapp_token or "",
            to=conv.phone,
            text=text,
        )

        now = datetime.now(timezone.utc)
        message = Message(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            sender_type=SenderType.BOT,
            content=text,
            message_type="text",
            status=MessageStatus.PROCESSED,
            created_at=now,
        )
        db.add(message)
        conv.idle_warning_sent_at = now
        conv.last_activity_at = now
        conv.updated_at = now
        await db.commit()
        await _publish_message(tenant.slug, conv.id, message)
        logger.info("Sent inactivity warning for conv %s", conv.id)


async def _close_conversation(tenant: Tenant, conv_id: uuid.UUID, cutoff: datetime) -> None:
    schema = f"t_{tenant.slug}"
    set_tenant_schema(schema)
    async with make_tenant_session(schema) as db:
        conv = await db.scalar(
            select(Conversation)
            .where(Conversation.id == conv_id)
            .with_for_update()
        )
        if (
            conv is None
            or conv.status not in (
                ConversationStatus.BOT_ACTIVE,
                ConversationStatus.HUMAN_ACTIVE,
            )
            or conv.idle_warning_sent_at is None
            or conv.idle_warning_sent_at > cutoff
            or not _window_open(conv.last_user_message_at)
        ):
            return

        latest = await _latest_message(db, conv.id)
        warning_sent_at = conv.idle_warning_sent_at
        if warning_sent_at.tzinfo is None:
            warning_sent_at = warning_sent_at.replace(tzinfo=timezone.utc)
        latest_created_at = latest.created_at if latest else None
        if latest_created_at and latest_created_at.tzinfo is None:
            latest_created_at = latest_created_at.replace(tzinfo=timezone.utc)
        if latest_created_at and latest_created_at > warning_sent_at:
            logger.info("Cancelled inactivity close for active conv %s", conv.id)
            return

        text = settings.CONVERSATION_IDLE_CLOSED_TEXT
        await send_text_message(
            phone_id=tenant.whatsapp_phone_id or "",
            token=tenant.whatsapp_token or "",
            to=conv.phone,
            text=text,
        )

        now = datetime.now(timezone.utc)
        message = Message(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            sender_type=SenderType.BOT,
            content=text,
            message_type="text",
            status=MessageStatus.PROCESSED,
            created_at=now,
        )
        db.add(message)
        conv.status = ConversationStatus.CLOSED
        conv.closed_at = now
        conv.updated_at = now
        conv.last_activity_at = now
        conv.idle_warning_sent_at = None
        await db.execute(
            update(Assignment)
            .where(
                Assignment.conversation_id == conv.id,
                Assignment.released_at.is_(None),
            )
            .values(released_at=now)
        )
        await db.commit()
        await _publish_message(tenant.slug, conv.id, message)
        await manager.publish(tenant.slug, {
            "type": "conversation_closed",
            "conversation_id": str(conv.id),
        })
        logger.info("Closed inactive conv %s", conv.id)


async def _close_waiting_conversation(
    tenant: Tenant,
    conv_id: uuid.UUID,
    timeout_cutoff: datetime,
    window_buffer_cutoff: datetime,
) -> None:
    schema = f"t_{tenant.slug}"
    set_tenant_schema(schema)
    async with make_tenant_session(schema) as db:
        conv = await db.scalar(
            select(Conversation)
            .where(Conversation.id == conv_id)
            .with_for_update()
        )
        if (
            conv is None
            or conv.status != ConversationStatus.WAITING_HUMAN
            or conv.handoff_notice_sent_at is None
            or conv.last_activity_at is None
            or conv.last_user_message_at is None
            or not _window_open(conv.last_user_message_at)
            or (
                conv.last_activity_at > timeout_cutoff
                and conv.last_user_message_at > window_buffer_cutoff
            )
        ):
            return

        text = settings.HUMAN_WAIT_TIMEOUT_TEXT
        await send_text_message(
            phone_id=tenant.whatsapp_phone_id or "",
            token=tenant.whatsapp_token or "",
            to=conv.phone,
            text=text,
        )

        now = datetime.now(timezone.utc)
        message = Message(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            sender_type=SenderType.BOT,
            content=text,
            message_type="text",
            status=MessageStatus.PROCESSED,
            created_at=now,
        )
        db.add(message)
        conv.status = ConversationStatus.CLOSED
        conv.assigned_agent_id = None
        conv.closed_at = now
        conv.updated_at = now
        conv.last_activity_at = now
        conv.idle_warning_sent_at = None
        await db.execute(
            update(Assignment)
            .where(
                Assignment.conversation_id == conv.id,
                Assignment.released_at.is_(None),
            )
            .values(released_at=now)
        )
        await db.commit()
        await _publish_message(tenant.slug, conv.id, message)
        await manager.publish(tenant.slug, {
            "type": "conversation_closed",
            "conversation_id": str(conv.id),
        })
        logger.info("Closed unassigned waiting conv %s", conv.id)


async def _close_expired_conversation(
    tenant_slug: str,
    conv_id: uuid.UUID,
    activity_cutoff: datetime,
) -> None:
    """Close stale state after Meta's window has expired; no free text is legal."""
    schema = f"t_{tenant_slug}"
    set_tenant_schema(schema)
    async with make_tenant_session(schema) as db:
        conv = await db.scalar(
            select(Conversation)
            .where(Conversation.id == conv_id)
            .with_for_update()
        )
        if (
            conv is None
            or conv.status not in (
                ConversationStatus.BOT_ACTIVE,
                ConversationStatus.HUMAN_ACTIVE,
                ConversationStatus.WAITING_HUMAN,
            )
            or conv.last_activity_at is None
            or conv.last_activity_at > activity_cutoff
            or _window_open(conv.last_user_message_at)
        ):
            return

        now = datetime.now(timezone.utc)
        conv.status = ConversationStatus.CLOSED
        conv.assigned_agent_id = None
        conv.closed_at = now
        conv.updated_at = now
        conv.last_activity_at = now
        conv.idle_warning_sent_at = None
        await db.execute(
            update(Assignment)
            .where(
                Assignment.conversation_id == conv.id,
                Assignment.released_at.is_(None),
            )
            .values(released_at=now)
        )
        await db.commit()
        await manager.publish(tenant_slug, {
            "type": "conversation_closed",
            "conversation_id": str(conv.id),
        })
        logger.warning(
            "Closed expired conv %s without WhatsApp text because its 24-hour window is closed",
            conv.id,
        )


async def _run_with_conversation_lock(redis, conv_id: uuid.UUID, operation, *args) -> bool:
    lock_token = await acquire_handoff_lock(redis, conv_id)
    if lock_token is None:
        return False
    try:
        await operation(*args)
        return True
    finally:
        await release_handoff_lock(redis, conv_id, lock_token)


async def _scan_once(redis) -> None:
    now = datetime.now(timezone.utc)
    warning_cutoff = now - timedelta(
        minutes=settings.CONVERSATION_IDLE_WARNING_MINUTES
    )
    close_cutoff = now - timedelta(
        minutes=settings.CONVERSATION_IDLE_GRACE_MINUTES
    )
    warning_window_cutoff = now - timedelta(
        hours=24,
        minutes=-settings.CONVERSATION_IDLE_GRACE_MINUTES,
    )
    close_window_cutoff = now - timedelta(hours=24)
    human_wait_cutoff = now - timedelta(minutes=settings.HUMAN_WAIT_TIMEOUT_MINUTES)
    human_wait_window_cutoff = now - timedelta(
        hours=24,
        minutes=-settings.HUMAN_WAIT_WINDOW_BUFFER_MINUTES,
    )
    expired_activity_cutoff = now - timedelta(
        minutes=settings.CONVERSATION_EXPIRED_CLEANUP_MINUTES
    )

    async with AsyncSessionLocal() as public_db:
        result = await public_db.execute(
            select(Tenant).where(
                Tenant.active == True,
                Tenant.whatsapp_phone_id.is_not(None),
                Tenant.whatsapp_token.is_not(None),
            )
        )
        tenants = result.scalars().all()

    for tenant in tenants:
        schema = f"t_{tenant.slug}"
        set_tenant_schema(schema)
        try:
            async with make_tenant_session(schema) as db:
                warning_ids = (
                    await db.scalars(
                        select(Conversation.id)
                        .where(
                            Conversation.status.in_([
                                ConversationStatus.BOT_ACTIVE,
                                ConversationStatus.HUMAN_ACTIVE,
                            ]),
                            Conversation.idle_warning_sent_at.is_(None),
                            Conversation.last_user_message_at.is_not(None),
                            Conversation.last_user_message_at >= warning_window_cutoff,
                            Conversation.last_activity_at.is_not(None),
                            Conversation.last_activity_at <= warning_cutoff,
                        )
                        .order_by(Conversation.last_activity_at.asc())
                        .limit(settings.CONVERSATION_IDLE_SCAN_BATCH)
                    )
                ).all()
                close_ids = (
                    await db.scalars(
                        select(Conversation.id)
                        .where(
                            Conversation.status.in_([
                                ConversationStatus.BOT_ACTIVE,
                                ConversationStatus.HUMAN_ACTIVE,
                            ]),
                            Conversation.idle_warning_sent_at.is_not(None),
                            Conversation.last_user_message_at.is_not(None),
                            Conversation.last_user_message_at >= close_window_cutoff,
                            Conversation.idle_warning_sent_at <= close_cutoff,
                        )
                        .order_by(Conversation.idle_warning_sent_at.asc())
                        .limit(settings.CONVERSATION_IDLE_SCAN_BATCH)
                    )
                ).all()
                waiting_ids = (
                    await db.scalars(
                        select(Conversation.id)
                        .where(
                            Conversation.status == ConversationStatus.WAITING_HUMAN,
                            Conversation.handoff_notice_sent_at.is_not(None),
                            Conversation.last_activity_at.is_not(None),
                            Conversation.last_user_message_at.is_not(None),
                            Conversation.last_user_message_at >= close_window_cutoff,
                            or_(
                                Conversation.last_activity_at <= human_wait_cutoff,
                                Conversation.last_user_message_at <= human_wait_window_cutoff,
                            ),
                        )
                        .order_by(Conversation.last_activity_at.asc())
                        .limit(settings.CONVERSATION_IDLE_SCAN_BATCH)
                    )
                ).all()
                expired_ids = (
                    await db.scalars(
                        select(Conversation.id)
                        .where(
                            Conversation.status.in_([
                                ConversationStatus.BOT_ACTIVE,
                                ConversationStatus.HUMAN_ACTIVE,
                                ConversationStatus.WAITING_HUMAN,
                            ]),
                            Conversation.last_activity_at.is_not(None),
                            Conversation.last_activity_at <= expired_activity_cutoff,
                            or_(
                                Conversation.last_user_message_at.is_(None),
                                Conversation.last_user_message_at < close_window_cutoff,
                            ),
                        )
                        .order_by(Conversation.last_activity_at.asc())
                        .limit(settings.CONVERSATION_IDLE_SCAN_BATCH)
                    )
                ).all()

            for conv_id in expired_ids:
                try:
                    await _run_with_conversation_lock(
                        redis,
                        conv_id,
                        _close_expired_conversation,
                        tenant.slug,
                        conv_id,
                        expired_activity_cutoff,
                    )
                except Exception:
                    logger.exception("Could not clean up expired conv %s", conv_id)

            for conv_id in waiting_ids:
                try:
                    await _run_with_conversation_lock(
                        redis,
                        conv_id,
                        _close_waiting_conversation,
                        tenant,
                        conv_id,
                        human_wait_cutoff,
                        human_wait_window_cutoff,
                    )
                except Exception:
                    logger.exception("Could not close waiting conv %s", conv_id)

            for conv_id in close_ids:
                try:
                    await _run_with_conversation_lock(
                        redis,
                        conv_id,
                        _close_conversation,
                        tenant,
                        conv_id,
                        close_cutoff,
                    )
                except Exception:
                    logger.exception("Could not close inactive conv %s", conv_id)

            for conv_id in warning_ids:
                try:
                    await _run_with_conversation_lock(
                        redis,
                        conv_id,
                        _warn_conversation,
                        tenant,
                        conv_id,
                        warning_cutoff,
                    )
                except Exception:
                    logger.exception("Could not warn inactive conv %s", conv_id)
        except Exception:
            logger.exception("Conversation lifecycle scan failed for tenant %s", tenant.slug)


async def run(stop_event: asyncio.Event) -> None:
    if not settings.CONVERSATION_IDLE_ENABLED:
        logger.info("conversation_lifecycle worker disabled")
        return

    redis = await get_redis()
    manager.set_redis(redis)
    lock_seconds = max(settings.CONVERSATION_IDLE_SCAN_SECONDS * 10, 300)
    logger.info(
        "conversation_lifecycle worker started (warning=%dm, close=%dm)",
        settings.CONVERSATION_IDLE_WARNING_MINUTES,
        settings.CONVERSATION_IDLE_GRACE_MINUTES,
    )

    while not stop_event.is_set():
        try:
            lock_token = str(uuid.uuid4())
            acquired = await redis.set(
                SCAN_LOCK, lock_token, nx=True, ex=lock_seconds
            )
            if acquired:
                try:
                    await _scan_once(redis)
                finally:
                    await redis.eval(
                        RELEASE_LOCK_SCRIPT, 1, SCAN_LOCK, lock_token
                    )
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("conversation_lifecycle loop error")

        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=settings.CONVERSATION_IDLE_SCAN_SECONDS
            )
        except asyncio.TimeoutError:
            pass

    await redis.aclose()
    logger.info("conversation_lifecycle worker stopped")