import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    slug: str = Field(..., min_length=2, max_length=60, pattern=r"^[a-z0-9_-]+$")
    whatsapp_phone_id: str | None = None
    whatsapp_token: str | None = None
    webhook_secret: str | None = None
    ai_system_prompt: str | None = None


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    whatsapp_phone_id: str | None = None
    whatsapp_token: str | None = None
    webhook_secret: str | None = None
    ai_system_prompt: str | None = None
