"""
Conversations API

GET    /conversations           — list (paginated, filterable by status)
GET    /conversations/{id}      — detail + messages
POST   /conversations/{id}/take — agent claims a WAITING_HUMAN conversation
POST   /conversations/{id}/close — close conversation
POST   /conversations/{id}/send — agent sends a message to the user
"""
import logging
import uuid
from datetime import datetime, timezone

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
    if conv.status not in (ConversationStatus.WAITING_HUMAN, ConversationStatus.BOT_ACTIVE):
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
