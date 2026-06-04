import math
import re
import uuid
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_platform_user, require_admin
from app.core.config import settings
from app.database import get_chat_db, get_db
from app.models.cliente import Cliente
from app.models.tipo_cliente import TipoCliente
from app.models.transaccion_procesada import TransaccionProcesada
from app.services.notification_queue import push as _push_notif
from app.services.suscripciones import renovar_cliente

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
    tipo_cliente: Optional[int] = None


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

    # IDs ya procesados (ocultos) en portal DB
    procesados: set[uuid.UUID] = set(
        db.execute(
            select(TransaccionProcesada.id_externo).where(TransaccionProcesada.estado == False)  # noqa: E712
        ).scalars().all()
    )

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

    # Filtrar filas ya procesadas
    rows = [r for r in rows if r["id"] not in procesados]

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
                tipo_cliente=cli.tipo_cliente if cli else None,
            ),
        ))

    pages = max(1, math.ceil(total / PAGE_SIZE))
    return PagedTransacciones(total=total, page=page, pages=pages, items=items)


# ── Helpers internos ──────────────────────────────────────────────────────────

def _marcar_procesada(db: Session, id_externo: uuid.UUID) -> None:
    """Inserta o actualiza el registro de transaccion procesada con estado=False."""
    existente = db.execute(
        select(TransaccionProcesada).where(TransaccionProcesada.id_externo == id_externo)
    ).scalar_one_or_none()
    if existente is None:
        db.add(TransaccionProcesada(id_externo=id_externo, estado=False))
    else:
        existente.estado = False
    db.commit()


def _get_phone_from_chat(chat_db: Session, schema: str, msg_id: uuid.UUID) -> Optional[str]:
    row = chat_db.execute(text(f"""
        SELECT c.phone
        FROM {schema}.messages m
        JOIN {schema}.conversations c ON c.id = m.conversation_id
        WHERE m.id = :msg_id
        LIMIT 1
    """), {"msg_id": msg_id}).mappings().first()
    return row["phone"] if row else None


# ── Acción: Eliminar (solo ocultar) ──────────────────────────────────────────

@router.post("/{id}/eliminar")
def eliminar_transaccion(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    _marcar_procesada(db, id)
    return {"ok": True}


# ── Acción: Renovar suscripción ───────────────────────────────────────────────

@router.post("/{id}/renovar")
def renovar_desde_transaccion(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    chat_db: Session = Depends(get_chat_db),
    user=Depends(require_admin),
):
    schema = settings.DATABASE_SCHEMA_2
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', schema):
        raise ValueError(f"Nombre de schema inválido: {schema}")

    phone_orig = _get_phone_from_chat(chat_db, schema, id)
    if not phone_orig:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado en la BD de chat")

    phone_local = _strip_country_code(phone_orig)
    cliente = db.execute(
        select(Cliente).where(Cliente.celular == phone_local)
    ).scalar_one_or_none()
    if not cliente:
        raise HTTPException(status_code=404, detail=f"Cliente con celular {phone_local} no registrado")

    if cliente.tipo_cliente != 1:
        raise HTTPException(status_code=400, detail="Solo se puede renovar clientes de tipo 1")

    nueva, era_vip = renovar_cliente(
        db=db,
        cliente=cliente,
        platform_user_id=user.id,
        usuario=user.usuario,
        audit_action="RENOVAR_TRANSACCION",
        audit_entity="transacciones",
        audit_entity_id=str(id),
    )

    _marcar_procesada(db, id)

    if not era_vip:
        from app.core.live_events import publish_event
        publish_event("nuevo_vip", {"nombre": cliente.nombre})

    return {"ok": True, "cliente": cliente.nombre, "nueva_fin": nueva.fin.isoformat()}


# ── Acción: Enviar mensaje WhatsApp ──────────────────────────────────────────

class MensajePayload(BaseModel):
    texto: str


@router.post("/{id}/mensaje")
def enviar_mensaje_transaccion(
    id: uuid.UUID,
    payload: MensajePayload,
    db: Session = Depends(get_db),
    chat_db: Session = Depends(get_chat_db),
    _user=Depends(require_admin),
):
    if not settings.WHATSAPP_CONTACTO_TRANSACCIONES:
        raise HTTPException(status_code=503, detail="WHATSAPP_CONTACTO_TRANSACCIONES no configurado")

    schema = settings.DATABASE_SCHEMA_2
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', schema):
        raise ValueError(f"Nombre de schema inválido: {schema}")

    phone_orig = _get_phone_from_chat(chat_db, schema, id)
    if not phone_orig:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado en la BD de chat")

    numero_dest = re.sub(r"\D", "", phone_orig)
    _push_notif("contacto_transacciones", numero_dest, {"texto": payload.texto})
    return {"ok": True}
