import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field


class OtpRequest(BaseModel):
    celular: str = Field(..., min_length=7, max_length=15)
    codigo_pais: str = Field(default='57', max_length=10)


class LoginRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    celular: str = Field(..., min_length=1, max_length=30)
    codigo_pais: str = Field(default='57', max_length=10)
    otp_code: str | None = Field(default=None, min_length=6, max_length=6)
    correo: str | None = Field(default=None, max_length=200)
    cc: str | None = Field(default=None, max_length=30)


class ClienteResponse(BaseModel):
    id: uuid.UUID
    nombre: str
    celular: str
    codigo_pais: str | None
    correo: str | None
    cc: str | None
    saldo: float
    vip: bool
    enabled: bool
    fecha_nacimiento: date | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    cliente: ClienteResponse
    es_nuevo: bool
    disabled_msg: str | None = None


class VipVerifyRequest(BaseModel):
    cliente_id: uuid.UUID
    codigo: str = Field(..., min_length=1, max_length=100)


class UpdateMisDatosRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    celular: str = Field(..., min_length=1, max_length=30)
    correo: str | None = Field(default=None, max_length=200)
    cc: str | None = Field(default=None, max_length=30)
    fecha_nacimiento: date | None = None
