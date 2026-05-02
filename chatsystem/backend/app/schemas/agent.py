import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.agent import AgentStatus


class AgentOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    email: str
    role: str
    status: AgentStatus
    max_concurrent_chats: int
    last_assigned_at: datetime | None = None
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = Field(default="agent", pattern="^(agent|admin)$")
    max_concurrent_chats: int = Field(default=5, ge=0, le=50)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8)
    role: str | None = Field(default=None, pattern="^(agent|admin)$")
    max_concurrent_chats: int | None = Field(default=None, ge=0, le=50)
    active: bool | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Legacy aliases
AgentStatusUpdate = AgentUpdate
AgentLoginIn = LoginRequest
AgentLoginOut = TokenOut
