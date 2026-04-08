import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    celular: str = Field(..., min_length=1, max_length=30)
    correo: str | None = Field(default=None, max_length=200)
    cc: str | None = Field(default=None, max_length=30)


class ClienteResponse(BaseModel):
    id: uuid.UUID
    nombre: str
    celular: str
    correo: str | None
    cc: str | None
    saldo: float
    vip: bool
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    cliente: ClienteResponse
    es_nuevo: bool


class VipVerifyRequest(BaseModel):
    cliente_id: uuid.UUID
    codigo: str = Field(..., min_length=1, max_length=100)


class UpdateMisDatosRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    celular: str = Field(..., min_length=1, max_length=30)
    correo: str | None = Field(default=None, max_length=200)
    cc: str | None = Field(default=None, max_length=30)
