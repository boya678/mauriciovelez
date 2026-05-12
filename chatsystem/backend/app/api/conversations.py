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
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.tenant import TenantContext, get_tenant_db, resolve_tenant, require_agent
from app.models.assignment import Assignment
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageStatus, SenderType
from app.redis.client import get_redis
from app.redis.streams import OUTGOING_STREAM, xadd
from app.services.message_stats import record_messages
from app.schemas.conversation import (
    ConversationDetail,
    ConversationOut,
)
from app.schemas.message import MessageOut
from app.services.whatsapp import send_template_message, send_text_message
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
    q = select(Conversation).where(Conversation.tenant_id == tenant.id)
    if status_filter:
        q = q.where(Conversation.status == status_filter)
    q = q.order_by(Conversation.updated_at.desc())
    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await db.scalars(q)
    convs = result.all()
    return [ConversationOut.model_validate(c) for c in convs]


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
            text="Un agente se pondrá en contacto contigo pronto.",
        )
        msg_content = "Un agente se pondrá en contacto contigo pronto."
        await db.execute(
            update(Conversation)
            .where(Conversation.id == closed_conv.id)
            .values(
                status=ConversationStatus.HUMAN_ACTIVE,
                assigned_agent_id=agent.id,
                closed_at=None,
                updated_at=now,
            )
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
    """Agent manually claims a WAITING_HUMAN conversation."""
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant.id,
        )
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.status not in (ConversationStatus.WAITING_HUMAN, ConversationStatus.BOT_ACTIVE, ConversationStatus.HUMAN_ACTIVE):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Conversation is {conv.status.value}, cannot take",
        )

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
    await db.commit()
    await db.refresh(conv)

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
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant.id,
        )
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    now = datetime.now(timezone.utc)
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(status=ConversationStatus.CLOSED, updated_at=now, closed_at=now)
    )
    await db.commit()
    await db.refresh(conv)

    await manager.publish(tenant.slug, {
        "type": "conversation_closed",
        "conversation_id": str(conversation_id),
    })
    return ConversationOut.model_validate(conv)


# ── Agent sends message ───────────────────────────────────────────────────────

class SendMessageBody(BaseModel):
    content: str


@router.post("/{conversation_id}/send", response_model=MessageOut)
async def send_message(
    conversation_id: uuid.UUID,
    body: SendMessageBody,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    agent=Depends(require_agent),
):
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant.id,
        )
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
    await xadd(redis, OUTGOING_STREAM, {
        "tenant_id": str(tenant.id),
        "tenant_slug": tenant.slug,
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
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant.id,
        )
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
            text="Un agente se pondrá en contacto contigo pronto.",
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
        "Un agente se pondrá en contacto contigo pronto."
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
