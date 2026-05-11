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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.tenant import TenantContext, get_tenant_db, resolve_tenant, require_agent
from app.models.assignment import Assignment
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageStatus, SenderType
from app.redis.client import get_redis
from app.redis.streams import OUTGOING_STREAM, xadd
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
    """Agent initiates an outbound conversation. Sends the tenant's WhatsApp template."""
    if not tenant.whatsapp_template_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tenant has no WhatsApp template configured. Set it in Settings.",
        )

    # Check for an existing open conversation with this number
    existing = await db.scalar(
        select(Conversation).where(
            Conversation.tenant_id == tenant.id,
            Conversation.phone == body.phone,
            Conversation.status != ConversationStatus.CLOSED,
        )
    )
    if existing:
        if existing.status == ConversationStatus.BOT_ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "bot_active", "conversation_id": str(existing.id)},
            )
        if existing.status == ConversationStatus.HUMAN_ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "human_active", "conversation_id": str(existing.id)},
            )
        if existing.status == ConversationStatus.WAITING_HUMAN:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "waiting_human", "conversation_id": str(existing.id)},
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An open conversation already exists for {body.phone}",
        )

    # Send template via WhatsApp
    await send_template_message(
        phone_id=tenant.whatsapp_phone_id,
        token=tenant.whatsapp_token,
        to=body.phone,
        template_name=tenant.whatsapp_template_name,
        language=tenant.whatsapp_template_language or "es",
    )

    now = datetime.now(timezone.utc)
    conv = Conversation(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        phone=body.phone,
        status=ConversationStatus.HUMAN_ACTIVE,
        assigned_agent_id=agent.id,
        created_at=now,
        updated_at=now,
    )
    db.add(conv)
    await db.flush()

    db.add(Assignment(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        agent_id=agent.id,
        assigned_at=now,
    ))
    await db.commit()
    await db.refresh(conv)

    await manager.publish(tenant.slug, {
        "type": "conversation_assigned",
        "conversation_id": str(conv.id),
        "agent_id": str(agent.id),
    })
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

    redis = await get_redis()
    await xadd(redis, OUTGOING_STREAM, {
        "tenant_id": str(tenant.id),
        "tenant_slug": tenant.slug,
        "phone": conv.phone,
        "message_id": str(msg.id),
        "content": body.content,
        "phone_id": tenant.whatsapp_phone_id,
        "token": tenant.whatsapp_token,
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
    closed_at = conv.closed_at
    within_24h = closed_at is not None and (now - closed_at) < timedelta(hours=24)

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
    return ConversationOut.model_validate(conv)
