import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SuperadminOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SuperadminCreate(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=8)


class SuperadminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class SuperadminTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
