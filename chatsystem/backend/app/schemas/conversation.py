import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, computed_field

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
    last_user_message_at: datetime | None = None

    @computed_field  # type: ignore[misc]
    @property
    def window_open(self) -> bool:
        if self.last_user_message_at is None:
            return False
        dt = self.last_user_message_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt) < timedelta(hours=24)

    model_config = {"from_attributes": True}


class ConversationList(BaseModel):
    items: list[ConversationOut]


class ConversationDetail(ConversationOut):
    messages: list[Any] = []


class TakeConversationIn(BaseModel):
    agent_id: uuid.UUID


class CloseConversationIn(BaseModel):
    reason: str | None = None
