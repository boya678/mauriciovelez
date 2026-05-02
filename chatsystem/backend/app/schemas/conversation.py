import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.conversation import ConversationStatus


class ConversationOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    phone: str
    status: ConversationStatus
    assigned_agent_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConversationList(BaseModel):
    items: list[ConversationOut]


class ConversationDetail(ConversationOut):
    messages: list[Any] = []


class TakeConversationIn(BaseModel):
    agent_id: uuid.UUID


class CloseConversationIn(BaseModel):
    reason: str | None = None
