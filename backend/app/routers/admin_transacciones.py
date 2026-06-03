import math
import re
import uuid
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_platform_user
from app.core.config import settings
from app.database import get_chat_db, get_db
from app.models.cliente import Cliente
from app.models.tipo_cliente import TipoCliente

router = APIRouter(prefix="/admin/transacciones", tags=["Admin Transacciones"])

COL_TZ = ZoneInfo("America/Bogota")


def _strip_country_code(phone: str) -> str:
    """Quita el código de país y devuelve los 10 dígitos locales colombianos."""
    digits = re.sub(r"\D", "", phone)
    # Formato típico WhatsApp Colombia: 573XXXXXXXXX (12 dígitos)
    if len(digits) == 12 and digits.startswith("57"):
        return digits[2:]
    # Si viene con prefijo 57 y tiene más/menos dígitos, tomar últimos 10
    if len(digits) > 10:
        return digits[-10:]
    return digits


# ── Schemas de respuesta ──────────────────────────────────────────────────────

class ClienteInfo(BaseModel):
    registrado: bool
    nombre: Optional[str] = None
    vip: Optional[bool] = None
    activo: Optional[bool] = None
    tipo_nombre: Optional[str] = None


PAGE_SIZE = 50


class TransaccionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    phone: str
    phone_local: str
    media_content: Optional[str] = None
    media_mime_type: Optional[str] = None
    imagen_descripcion: Optional[str] = None
    cliente: ClienteInfo

    model_config = {"from_attributes": True}


class PagedTransacciones(BaseModel):
    total: int
    page: int
    pages: int
    items: list[TransaccionOut]


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("", response_model=PagedTransacciones)
def get_transacciones(
    fecha: Optional[date] = Query(default=None, description="Fecha YYYY-MM-DD (default: hoy en Colombia)"),
    page: int = Query(default=1, ge=1, description="Página (1-based)"),
    _user=Depends(get_current_platform_user),
    db: Session = Depends(get_db),
    chat_db: Session = Depends(get_chat_db),
):
    if fecha is None:
        fecha = datetime.now(COL_TZ).date()

    schema = settings.DATABASE_SCHEMA_2
    # Validar que el nombre de schema sea seguro (solo letras, dígitos, _)
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', schema):
        raise ValueError(f"Nombre de schema inválido: {schema}")

    base_where = f"""
        FROM {schema}.messages m
        JOIN {schema}.conversations c ON c.id = m.conversation_id
        WHERE m.message_type = 'image'
          AND (m.created_at AT TIME ZONE 'America/Bogota')::date = :fecha
    """

    total: int = chat_db.execute(
        text(f"SELECT COUNT(*) {base_where}"), {"fecha": fecha}
    ).scalar_one()

    offset = (page - 1) * PAGE_SIZE
    rows = chat_db.execute(text(f"""
        SELECT
            m.id,
            m.media_content,
            m.media_mime_type,
            m.imagen_descripcion,
            m.created_at,
            c.phone
        {base_where}
        ORDER BY m.created_at ASC
        LIMIT {PAGE_SIZE} OFFSET :offset
    """), {"fecha": fecha, "offset": offset}).mappings().all()

    # Batch lookup de clientes por número local
    local_phones = list({_strip_country_code(r["phone"] or "") for r in rows if r["phone"]})
    clientes_map: dict[str, Cliente] = {}
    tipos_map: dict[int, str] = {}
    if local_phones:
        found = db.execute(
            select(Cliente).where(Cliente.celular.in_(local_phones))
        ).scalars().all()
        for c in found:
            clientes_map[c.celular] = c
        tipo_ids = {c.tipo_cliente for c in found if c.tipo_cliente}
        if tipo_ids:
            tipos = db.execute(
                select(TipoCliente).where(TipoCliente.id.in_(tipo_ids))
            ).scalars().all()
            tipos_map = {t.id: t.nombre for t in tipos}

    items: list[TransaccionOut] = []
    for row in rows:
        phone_orig = row["phone"] or ""
        phone_local = _strip_country_code(phone_orig)
        cli = clientes_map.get(phone_local)

        items.append(TransaccionOut(
            id=row["id"],
            created_at=row["created_at"],
            phone=phone_orig,
            phone_local=phone_local,
            media_content=row["media_content"],
            media_mime_type=row["media_mime_type"],
            imagen_descripcion=row["imagen_descripcion"],
            cliente=ClienteInfo(
                registrado=cli is not None,
                nombre=cli.nombre if cli else None,
                vip=cli.vip if cli else None,
                activo=cli.enabled if cli else None,
                tipo_nombre=tipos_map.get(cli.tipo_cliente) if cli else None,
            ),
        ))

    pages = max(1, math.ceil(total / PAGE_SIZE))
    return PagedTransacciones(total=total, page=page, pages=pages, items=items)
