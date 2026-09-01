"""
Conversations API

GET    /conversations           — list (paginated, filterable by status)
GET    /conversations/{id}      — detail + messages
POST   /conversations           — agent starts a new outbound conversation
POST   /conversations/{id}/take — agent claims a WAITING_HUMAN conversation
POST   /conversations/{id}/close — close conversation
POST   /conversations/{id}/reopen — reopen a closed conversation
POST   /conversations/{id}/send — agent sends a message to the user
"""
import logging
import base64
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from pydantic import BaseModel
from sqlalchemy import desc, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.db.tenant import TenantContext, get_tenant_db, resolve_tenant, require_agent
from app.models.assignment import Assignment
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageStatus, SenderType
from app.redis.client import get_redis
from app.redis.streams import OUTGOING_STREAM, xadd
from app.services.message_stats import record_messages
from app.services.conversation_start_lock import acquire_conversation_start_lock
from app.services.handoff_lock import acquire_handoff_lock, release_handoff_lock
from app.schemas.conversation import (
    ConversationDetail,
    ConversationOut,
)
from app.schemas.message import MessageOut
from app.services.whatsapp import send_template_message, send_text_message, send_request_contact_info
from app.websocket.manager import manager

router = APIRouter(prefix="/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    status_filter: ConversationStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    _agent=Depends(require_agent),
):
    from sqlalchemy import text as _text
    schema = tenant.schema
    offset = (page - 1) * page_size
    status_clause = "AND c.status = :status" if status_filter else ""
    rows = (await db.execute(
        _text(f"""
            SELECT c.id, c.tenant_id, c.phone, c.status, c.assigned_agent_id,
                   c.created_at, c.updated_at, c.closed_at, c.last_user_message_at,
                   ct.tags
            FROM {schema}.conversations c
            LEFT JOIN {schema}.contactos ct ON ct.id = c.phone
            WHERE c.tenant_id = :tenant_id {status_clause}
            ORDER BY c.updated_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"tenant_id": str(tenant.id), "status": status_filter, "limit": page_size, "offset": offset},
    )).mappings().all()

    return [
        ConversationOut(
            id=r["id"],
            tenant_id=r["tenant_id"],
            phone=r["phone"],
            status=r["status"],
            assigned_agent_id=r["assigned_agent_id"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            closed_at=r["closed_at"],
            last_user_message_at=r["last_user_message_at"],
            tags=r["tags"],
        )
        for r in rows
    ]


# ── Start outbound conversation ───────────────────────────────────────────────

class StartConversationBody(BaseModel):
    phone: str


@router.post("", response_model=ConversationOut, status_code=201)
async def start_conversation(
    body: StartConversationBody,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    agent=Depends(require_agent),
):
    """Agent initiates an outbound conversation.
    - Open conversation exists → 409 (redirect agent to that conversation)
    - Closed conversation within 24 h window → reopen + send text (no template needed)
    - No conversation / window expired → create new + send template
    """
    # Serialize concurrent starts for the same tenant + phone. The transaction
    # lock is released automatically on commit/rollback, including exceptions.
    await acquire_conversation_start_lock(db, tenant.id, body.phone)

    # ── 1. Check for an existing OPEN conversation ────────────────────────────
    existing = await db.scalar(
        select(Conversation).where(
            Conversation.tenant_id == tenant.id,
            Conversation.phone == body.phone,
            Conversation.status != ConversationStatus.CLOSED,
        )
    )
    if existing:
        code_map = {
            ConversationStatus.BOT_ACTIVE: "bot_active",
            ConversationStatus.HUMAN_ACTIVE: "human_active",
            ConversationStatus.WAITING_HUMAN: "waiting_human",
        }
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": code_map.get(existing.status, "open"),
                "conversation_id": str(existing.id),
            },
        )

    now = datetime.now(timezone.utc)

    # ── 2. Check for the most recent CLOSED conversation ─────────────────────
    closed_conv = await db.scalar(
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant.id,
            Conversation.phone == body.phone,
            Conversation.status == ConversationStatus.CLOSED,
        )
        .order_by(desc(Conversation.updated_at))
        .limit(1)
        .with_for_update()
    )

    last_user_ts = (closed_conv.last_user_message_at if closed_conv else None)
    if last_user_ts and last_user_ts.tzinfo is None:
        last_user_ts = last_user_ts.replace(tzinfo=timezone.utc)
    within_24h = last_user_ts is not None and (now - last_user_ts) < timedelta(hours=24)

    if within_24h and closed_conv is not None:
        # ── 2a. Window open → reopen closed conversation + send text ─────────
        await send_text_message(
            phone_id=tenant.whatsapp_phone_id,
            token=tenant.whatsapp_token,
            to=body.phone,
            text=settings.HUMAN_HANDOFF_NOTICE_TEXT,
        )
        msg_content = settings.HUMAN_HANDOFF_NOTICE_TEXT
        reopen_result = await db.execute(
            update(Conversation)
            .where(
                Conversation.id == closed_conv.id,
                Conversation.status == ConversationStatus.CLOSED,
            )
            .values(
                status=ConversationStatus.HUMAN_ACTIVE,
                assigned_agent_id=agent.id,
                closed_at=None,
                updated_at=now,
                last_activity_at=now,
                idle_warning_sent_at=None,
                handoff_notice_sent_at=now,
            )
        )
        if reopen_result.rowcount != 1:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La conversación cambió de estado; vuelve a intentarlo.",
            )
        conv_id = closed_conv.id
    else:
        # ── 2b. Window expired or no history → create new + send template ────
        if not tenant.whatsapp_template_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Tenant has no WhatsApp template configured. Set it in Settings.",
            )
        try:
            await send_template_message(
                phone_id=tenant.whatsapp_phone_id,
                token=tenant.whatsapp_token,
                to=body.phone,
                template_name=tenant.whatsapp_template_name,
                language=tenant.whatsapp_template_language or "es",
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            try:
                detail = exc.response.json().get("error", {}).get("error_data", {}).get("details") or exc.response.json().get("error", {}).get("message") or detail
            except Exception:
                pass
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
        msg_content = f"[Plantilla: {tenant.whatsapp_template_name}]"
        new_conv = Conversation(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            phone=body.phone,
            status=ConversationStatus.HUMAN_ACTIVE,
            assigned_agent_id=agent.id,
            created_at=now,
            updated_at=now,
            last_activity_at=now,
            idle_warning_sent_at=None,
            handoff_notice_sent_at=now,
        )
        db.add(new_conv)
        await db.flush()
        conv_id = new_conv.id

    db.add(Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        sender_type=SenderType.HUMAN,
        content=msg_content,
        status=MessageStatus.PROCESSED,
        created_at=now,
    ))
    db.add(Assignment(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        agent_id=agent.id,
        assigned_at=now,
    ))
    await db.commit()

    conv = await db.scalar(
        select(Conversation).where(Conversation.id == conv_id)
    )

    await manager.publish(tenant.slug, {
        "type": "conversation_assigned",
        "conversation_id": str(conv_id),
        "agent_id": str(agent.id),
    })

    # Accumulate human message counter (fire-and-forget)
    try:
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as stats_db:
            await record_messages(tenant.id, stats_db, human=1)
    except Exception:
        pass

    return ConversationOut.model_validate(conv)


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    _agent=Depends(require_agent),
):
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant.id,
        )
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs = await db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return ConversationDetail(
        **ConversationOut.model_validate(conv).model_dump(),
        messages=[MessageOut.model_validate(m) for m in msgs.all()],
    )


# ── Take ──────────────────────────────────────────────────────────────────────

@router.post("/{conversation_id}/take", response_model=ConversationOut)
async def take_conversation(
    conversation_id: uuid.UUID,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    agent=Depends(require_agent),
):
    redis = await get_redis()
    lock_token = await acquire_handoff_lock(redis, conversation_id)
    if lock_token is None:
        raise HTTPException(
            status_code=409,
            detail="La transferencia de esta conversación ya está en proceso.",
        )
    try:
        return await _take_conversation_locked(conversation_id, tenant, db, agent)
    finally:
        await release_handoff_lock(redis, conversation_id, lock_token)


async def _take_conversation_locked(
    conversation_id: uuid.UUID,
    tenant: TenantContext,
    db: AsyncSession,
    agent,
):
    """Agent manually claims a WAITING_HUMAN conversation."""
    conv = await db.scalar(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant.id,
        )
        .with_for_update()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.status not in (ConversationStatus.WAITING_HUMAN, ConversationStatus.BOT_ACTIVE, ConversationStatus.HUMAN_ACTIVE):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Conversation is {conv.status.value}, cannot take",
        )

    if conv.status == ConversationStatus.BOT_ACTIVE:
        pending_bot_message = await db.scalar(
            select(Message.id)
            .where(
                Message.conversation_id == conversation_id,
                Message.sender_type == SenderType.BOT,
                Message.status == MessageStatus.PENDING,
            )
            .limit(1)
        )
        if pending_bot_message is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "El bot tiene una respuesta en proceso. Espera a que termine "
                    "antes de tomar la conversación."
                ),
            )

    now = datetime.now(timezone.utc)
    last_user_ts = conv.last_user_message_at
    if last_user_ts and last_user_ts.tzinfo is None:
        last_user_ts = last_user_ts.replace(tzinfo=timezone.utc)
    window_open = (
        last_user_ts is not None
        and now - last_user_ts < timedelta(hours=24)
    )
    if conv.status != ConversationStatus.HUMAN_ACTIVE and not window_open:
        raise HTTPException(
            status_code=409,
            detail=(
                "La ventana de 24 horas está cerrada. No se asignó la conversación; "
                "se requiere una plantilla aprobada y una nueva respuesta del usuario."
            ),
        )

    handoff_message: Message | None = None
    needs_notice = (
        conv.status in (ConversationStatus.WAITING_HUMAN, ConversationStatus.BOT_ACTIVE)
        and conv.handoff_notice_sent_at is None
    )
    if needs_notice:
        try:
            await send_text_message(
                phone_id=tenant.whatsapp_phone_id,
                token=tenant.whatsapp_token,
                to=conv.phone,
                text=settings.HUMAN_HANDOFF_NOTICE_TEXT,
            )
        except Exception as exc:
            logger.exception("Could not notify user before taking conv %s", conversation_id)
            raise HTTPException(
                status_code=502,
                detail="No se pudo avisar al usuario; la conversación no fue asignada.",
            ) from exc

        handoff_message = Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            sender_type=SenderType.BOT,
            content=settings.HUMAN_HANDOFF_NOTICE_TEXT,
            message_type="text",
            status=MessageStatus.PROCESSED,
            created_at=now,
        )
        db.add(handoff_message)

    update_values: dict = {
        "assigned_agent_id": agent.id,
        "status": ConversationStatus.HUMAN_ACTIVE,
        "updated_at": now,
    }
    if needs_notice:
        update_values.update({
            "handoff_notice_sent_at": now,
            "last_activity_at": now,
            "idle_warning_sent_at": None,
        })
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(**update_values)
    )
    db.add(Assignment(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        agent_id=agent.id,
        assigned_at=now,
    ))
    await db.commit()
    await db.refresh(conv)

    if handoff_message is not None:
        await manager.publish(tenant.slug, {
            "type": "new_message",
            "conversation_id": str(conversation_id),
            "message": {
                "id": str(handoff_message.id),
                "content": handoff_message.content,
                "sender_type": SenderType.BOT.value,
                "message_type": "text",
                "created_at": now.isoformat(),
            },
        })
    await manager.publish(tenant.slug, {
        "type": "conversation_assigned",
        "conversation_id": str(conversation_id),
        "agent_id": str(agent.id),
    })
    return ConversationOut.model_validate(conv)


# ── Close ─────────────────────────────────────────────────────────────────────

@router.post("/{conversation_id}/close", response_model=ConversationOut)
async def close_conversation(
    conversation_id: uuid.UUID,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    agent=Depends(require_agent),
):
    redis = await get_redis()
    lock_token = await acquire_handoff_lock(redis, conversation_id)
    if lock_token is None:
        raise HTTPException(
            status_code=409,
            detail="La conversación tiene otra acción en proceso. Intenta nuevamente.",
        )
    try:
        return await _close_conversation_locked(conversation_id, tenant, db, agent)
    finally:
        await release_handoff_lock(redis, conversation_id, lock_token)


async def _close_conversation_locked(
    conversation_id: uuid.UUID,
    tenant: TenantContext,
    db: AsyncSession,
    agent,
):
    conv = await db.scalar(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant.id,
        )
        .with_for_update()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.status == ConversationStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Conversation is already closed")

    now = datetime.now(timezone.utc)
    last_user_ts = conv.last_user_message_at
    if last_user_ts and last_user_ts.tzinfo is None:
        last_user_ts = last_user_ts.replace(tzinfo=timezone.utc)
    window_open = (
        last_user_ts is not None
        and now - last_user_ts < timedelta(hours=24)
    )
    if not window_open:
        raise HTTPException(
            status_code=409,
            detail=(
                "La ventana de 24 horas está cerrada. Para cerrar avisando al usuario "
                "se requiere una plantilla de cierre aprobada en Meta."
            ),
        )
    close_message: Message | None = None
    try:
        await send_text_message(
            phone_id=tenant.whatsapp_phone_id,
            token=tenant.whatsapp_token,
            to=conv.phone,
            text=settings.MANUAL_CLOSE_NOTICE_TEXT,
        )
    except Exception as exc:
        logger.exception("Could not notify user before closing conv %s", conversation_id)
        raise HTTPException(
            status_code=502,
            detail="No se pudo avisar al usuario; la conversación no fue cerrada.",
        ) from exc

    close_message = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        sender_type=SenderType.BOT,
        content=settings.MANUAL_CLOSE_NOTICE_TEXT,
        message_type="text",
        status=MessageStatus.PROCESSED,
        created_at=now,
    )
    db.add(close_message)

    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(
            status=ConversationStatus.CLOSED,
            assigned_agent_id=None,
            updated_at=now,
            closed_at=now,
            last_activity_at=now,
            idle_warning_sent_at=None,
        )
    )
    await db.execute(
        update(Assignment)
        .where(
            Assignment.conversation_id == conversation_id,
            Assignment.released_at.is_(None),
        )
        .values(released_at=now)
    )
    await db.commit()
    await db.refresh(conv)

    if close_message is not None:
        await manager.publish(tenant.slug, {
            "type": "new_message",
            "conversation_id": str(conversation_id),
            "message": {
                "id": str(close_message.id),
                "content": close_message.content,
                "sender_type": SenderType.BOT.value,
                "message_type": "text",
                "created_at": now.isoformat(),
            },
        })
    await manager.publish(tenant.slug, {
        "type": "conversation_closed",
        "conversation_id": str(conversation_id),
    })
    return ConversationOut.model_validate(conv)


# ── pedir_contacto ────────────────────────────────────────────────────────────

@router.post("/{conversation_id}/pedir-contacto")
async def pedir_contacto(
    conversation_id: uuid.UUID,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    agent=Depends(require_agent),
):
    """Send a REQUEST_CONTACT_INFO interactive message to a BSUID user.

    Only useful when the conversation has no real phone number yet
    (phone field is a BSUID). Once the user taps the button, Meta sends
    a contacts webhook that triggers updating conversation.phone with
    the real number.
    """
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant.id,
        )
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Only send if phone is still a BSUID (contains ".").
    # Once we have the real phone there's no need to ask again.
    if "." not in (conv.phone or ""):
        raise HTTPException(
            status_code=400,
            detail="Phone number already known — no need to request contact info",
        )

    try:
        await send_request_contact_info(
            phone_id=tenant.whatsapp_phone_id,
            token=tenant.whatsapp_token,
            to=conv.phone,  # may be BSUID or real phone; _to_field() handles both
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"WhatsApp error: {exc}")

    return {"status": "sent"}


# ── Agent sends message ───────────────────────────────────────────────────────

class SendMessageBody(BaseModel):
    content: str


async def _publish_outgoing_or_fail(
    db: AsyncSession,
    redis,
    message_id: uuid.UUID,
    payload: dict,
) -> None:
    try:
        await xadd(redis, OUTGOING_STREAM, payload)
    except Exception as exc:
        await db.execute(
            update(Message)
            .where(Message.id == message_id)
            .values(status=MessageStatus.ERROR)
        )
        await db.commit()
        logger.exception("Could not enqueue outgoing message %s", message_id)
        raise HTTPException(
            status_code=503,
            detail=(
                "No se pudo poner el mensaje en la cola y no fue enviado. "
                "Intenta nuevamente."
            ),
        ) from exc


ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_AUDIO_MIME_TYPES = {"audio/ogg", "audio/mpeg", "audio/mp4", "audio/webm", "video/webm"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_AUDIO_BYTES = 16 * 1024 * 1024

EXTENSION_TO_MIME: dict[str, str] = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "ogg": "audio/ogg",
    "mp3": "audio/mpeg",
    "mp4": "audio/mp4",
    "m4a": "audio/mp4",
    "webm": "audio/webm",
}


@router.post("/{conversation_id}/send", response_model=MessageOut)
async def send_message(
    conversation_id: uuid.UUID,
    body: SendMessageBody,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    agent=Depends(require_agent),
):
    conv = await db.scalar(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant.id,
        )
        .with_for_update()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.status == ConversationStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Conversation is closed")

    now = datetime.now(timezone.utc)
    msg = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        sender_type=SenderType.HUMAN,
        content=body.content,
        status=MessageStatus.PENDING,
        created_at=now,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    # Compute 24-hour messaging window
    last_user_ts = conv.last_user_message_at
    if last_user_ts and last_user_ts.tzinfo is None:
        last_user_ts = last_user_ts.replace(tzinfo=timezone.utc)
    window_open = last_user_ts is not None and (now - last_user_ts) < timedelta(hours=24)

    redis = await get_redis()
    await _publish_outgoing_or_fail(db, redis, msg.id, {
        "tenant_id": str(tenant.id),
        "tenant_slug": tenant.slug,
        "conversation_id": str(conversation_id),
        "phone": conv.phone,
        "message_id": str(msg.id),
        "content": body.content,
        "phone_id": tenant.whatsapp_phone_id,
        "token": tenant.whatsapp_token,
        "window_open": "1" if window_open else "0",
        "template_name": tenant.whatsapp_template_name or "",
        "template_language": tenant.whatsapp_template_language or "es",
    })

    await manager.publish(tenant.slug, {
        "type": "new_message",
        "conversation_id": str(conversation_id),
        "message": {
            "id": str(msg.id),
            "content": body.content,
            "sender_type": SenderType.HUMAN.value,
            "created_at": now.isoformat(),
        },
    })

    # Accumulate human message counter (fire-and-forget, non-blocking)
    try:
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as stats_db:
            await record_messages(tenant.id, stats_db, human=1)
    except Exception:
        pass  # stats are best-effort

    return MessageOut.model_validate(msg)


@router.post("/{conversation_id}/send-media", response_model=MessageOut)
async def send_media_message(
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),
    caption: str = Form(""),
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    agent=Depends(require_agent),
):
    conv = await db.scalar(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant.id,
        )
        .with_for_update()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.status == ConversationStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Conversation is closed")

    now = datetime.now(timezone.utc)
    last_user_ts = conv.last_user_message_at
    if last_user_ts and last_user_ts.tzinfo is None:
        last_user_ts = last_user_ts.replace(tzinfo=timezone.utc)
    window_open = last_user_ts is not None and (now - last_user_ts) < timedelta(hours=24)
    if not window_open:
        raise HTTPException(
            status_code=409,
            detail="La ventana de 24 h está cerrada; primero reabre con plantilla.",
        )

    raw_mime_type = (file.content_type or "").lower().strip()
    mime_type = raw_mime_type.split(";", 1)[0].strip()
    # Always try extension fallback if the mime type is unrecognized or generic.
    if (
        not mime_type
        or mime_type == "application/octet-stream"
        or (mime_type not in ALLOWED_IMAGE_MIME_TYPES and mime_type not in ALLOWED_AUDIO_MIME_TYPES)
    ):
        _filename = (file.filename or "").lower().strip()
        _ext = _filename.rsplit(".", 1)[-1] if "." in _filename else ""
        mime_type = EXTENSION_TO_MIME.get(_ext, mime_type)
    if mime_type in ALLOWED_IMAGE_MIME_TYPES:
        message_type = "image"
        max_bytes = MAX_IMAGE_BYTES
        content = caption.strip() or "[imagen]"
        default_filename = "image.jpg"
    elif mime_type in ALLOWED_AUDIO_MIME_TYPES:
        message_type = "audio"
        max_bytes = MAX_AUDIO_BYTES
        content = "[audio]"
        default_filename = "audio.ogg"
    else:
        raise HTTPException(status_code=415, detail="Tipo de archivo no soportado")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Archivo vacío")
    if len(raw) > max_bytes:
        raise HTTPException(status_code=413, detail="Archivo supera el tamaño permitido")

    media_content_b64 = base64.b64encode(raw).decode("ascii")
    media_filename = file.filename or default_filename

    msg = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        sender_type=SenderType.HUMAN,
        content=content,
        message_type=message_type,
        media_content=media_content_b64,
        media_mime_type=mime_type,
        status=MessageStatus.PENDING,
        created_at=now,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    redis = await get_redis()
    await _publish_outgoing_or_fail(db, redis, msg.id, {
        "tenant_id": str(tenant.id),
        "tenant_slug": tenant.slug,
        "conversation_id": str(conversation_id),
        "phone": conv.phone,
        "message_id": str(msg.id),
        "content": content,
        "message_type": message_type,
        "media_content": media_content_b64,
        "media_mime_type": mime_type,
        "media_filename": media_filename,
        "phone_id": tenant.whatsapp_phone_id,
        "token": tenant.whatsapp_token,
        "window_open": "1",
    })

    await manager.publish(tenant.slug, {
        "type": "new_message",
        "conversation_id": str(conversation_id),
        "message": {
            "id": str(msg.id),
            "content": content,
            "sender_type": SenderType.HUMAN.value,
            "message_type": message_type,
            "media_content": media_content_b64,
            "media_mime_type": mime_type,
            "created_at": now.isoformat(),
        },
    })

    try:
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as stats_db:
            await record_messages(tenant.id, stats_db, human=1)
    except Exception:
        pass

    return MessageOut.model_validate(msg)


# ── Reopen conversation ───────────────────────────────────────────────────────

@router.post("/{conversation_id}/reopen", response_model=ConversationOut)
async def reopen_conversation(
    conversation_id: uuid.UUID,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    agent=Depends(require_agent),
):
    """Reopen a closed conversation. Sends text if within 24 h, template otherwise."""
    conv = await db.scalar(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant.id,
        )
        .with_for_update()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.status != ConversationStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Conversation is not closed")

    now = datetime.now(timezone.utc)
    last_user_ts = conv.last_user_message_at
    if last_user_ts and last_user_ts.tzinfo is None:
        last_user_ts = last_user_ts.replace(tzinfo=timezone.utc)
    within_24h = last_user_ts is not None and (now - last_user_ts) < timedelta(hours=24)

    if within_24h:
        await send_text_message(
            phone_id=tenant.whatsapp_phone_id,
            token=tenant.whatsapp_token,
            to=conv.phone,
            text=settings.HUMAN_HANDOFF_NOTICE_TEXT,
        )
    else:
        if not tenant.whatsapp_template_name:
            raise HTTPException(
                status_code=422,
                detail="Tenant has no WhatsApp template configured. Set it in Settings.",
            )
        await send_template_message(
            phone_id=tenant.whatsapp_phone_id,
            token=tenant.whatsapp_token,
            to=conv.phone,
            template_name=tenant.whatsapp_template_name,
            language=tenant.whatsapp_template_language or "es",
        )

    reopen_content = (
        settings.HUMAN_HANDOFF_NOTICE_TEXT
        if within_24h
        else f"[Plantilla: {tenant.whatsapp_template_name}]"
    )
    db.add(Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        sender_type=SenderType.HUMAN,
        content=reopen_content,
        status=MessageStatus.PROCESSED,
        created_at=now,
    ))

    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(
            status=ConversationStatus.HUMAN_ACTIVE,
            assigned_agent_id=agent.id,
            closed_at=None,
            updated_at=now,
            last_activity_at=now,
            idle_warning_sent_at=None,
            handoff_notice_sent_at=now,
        )
    )
    db.add(Assignment(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        agent_id=agent.id,
        assigned_at=now,
    ))
    await db.commit()
    await db.refresh(conv)

    await manager.publish(tenant.slug, {
        "type": "conversation_assigned",
        "conversation_id": str(conversation_id),
        "agent_id": str(agent.id),
    })

    # Accumulate human message counter (fire-and-forget)
    try:
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as stats_db:
            await record_messages(tenant.id, stats_db, human=1)
    except Exception:
        pass

    return ConversationOut.model_validate(conv)
