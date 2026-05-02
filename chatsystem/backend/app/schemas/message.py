import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.message import MessageStatus, SenderType


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    external_id: str | None = None
    sender_type: SenderType
    content: str
    message_type: str
    status: MessageStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class SendMessageIn(BaseModel):
    content: str
    message_type: str = "text"
