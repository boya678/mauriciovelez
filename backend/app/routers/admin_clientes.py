import io
import uuid
from datetime import datetime, timezone
from typing import Optional

import openpyxl
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_platform_user, require_admin, require_edit
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.cliente import Cliente
from app.models.suscripcion import Suscripcion
from app.models.cuenta_vip import acumular_cuenta_vip

router = APIRouter(prefix="/admin/clientes", tags=["Admin Clientes"])


# ── Schemas ─────────────────────────────────────────────────────────────────────

class ClienteOut(BaseModel):
    id: uuid.UUID
    nombre: str
    celular: str
    correo: Optional[str]
    cc: Optional[str]
    saldo: float
    vip: bool
    codigo_vip: Optional[str]

    model_config = {"from_attributes": True}


class ClienteUpdate(BaseModel):
    nombre: Optional[str] = None
    correo: Optional[str] = None
    cc: Optional[str] = None
    saldo: Optional[float] = None
    vip: Optional[bool] = None
    codigo_vip: Optional[str] = None


class ClienteCreate(BaseModel):
    nombre: str
    celular: str
    correo: Optional[str] = None
    cc: Optional[str] = None
    saldo: float = 0
    vip: bool = False
    codigo_vip: Optional[str] = None


class PaginatedClientes(BaseModel):
    total: int
    page: int
    size: int
    items: list[ClienteOut]


# ── Helper audit ─────────────────────────────────────────────────────────────────

def _audit(db: Session, user, action: str, entity_id: str, detail: dict):
    db.add(AuditLog(
        platform_user_id=user.id,
        usuario=user.usuario,
        action=action,
        entity="clientes",
        entity_id=entity_id,
        detail=detail,
    ))


# ── Endpoints ────────────────────────────────────────────────────────────────────

@router.post("", response_model=ClienteOut, status_code=201)
def create_cliente(
    payload: ClienteCreate,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    nuevo = Cliente(
        id=uuid.uuid4(),
        nombre=payload.nombre,
        celular=payload.celular,
        correo=payload.correo or None,
        cc=payload.cc or None,
        saldo=payload.saldo,
        vip=payload.vip,
        codigo_vip=payload.codigo_vip or None,
    )
    db.add(nuevo)
    if payload.vip:
        now = datetime.now(timezone.utc)
        db.add(Suscripcion(
            cliente_id=nuevo.id,
            inicio=now,
            fin=now + relativedelta(months=1),
            activa=True,
        ))
        acumular_cuenta_vip(db)
    _audit(db, user, "CREATE", str(nuevo.id), {"nombre": nuevo.nombre, "celular": nuevo.celular})
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        orig = str(e.orig)
        if "celular" in orig:
            raise HTTPException(status_code=409, detail="Ya existe un cliente con ese número de celular")
        if "codigo_vip" in orig:
            raise HTTPException(status_code=409, detail="El código VIP ya está en uso por otro cliente")
        raise HTTPException(status_code=409, detail="Conflicto de datos: valor duplicado")
    db.refresh(nuevo)
    return nuevo


@router.get("", response_model=PaginatedClientes)
def list_clientes(
    q: Optional[str] = Query(None, description="Buscar por nombre, celular o cc"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    query = db.query(Cliente)
    if q:
        like = f"%{q}%"
        query = query.filter(
            Cliente.nombre.ilike(like)
            | Cliente.celular.ilike(like)
            | Cliente.cc.ilike(like)
        )
    total = query.count()
    items = query.order_by(Cliente.nombre).offset((page - 1) * size).limit(size).all()
    return PaginatedClientes(total=total, page=page, size=size, items=items)


@router.get("/export")
def export_clientes(
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    query = db.query(Cliente)
    if q:
        like = f"%{q}%"
        query = query.filter(
            Cliente.nombre.ilike(like)
            | Cliente.celular.ilike(like)
            | Cliente.cc.ilike(like)
        )
    items = query.order_by(Cliente.nombre).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Clientes"
    ws.append(["Nombre", "Celular", "CC", "Correo", "Saldo", "VIP", "Código VIP"])
    for c in items:
        ws.append([c.nombre, c.celular, c.cc or "", c.correo or "", float(c.saldo), "Sí" if c.vip else "No", c.codigo_vip or ""])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=clientes.xlsx"},
    )


@router.get("/{cliente_id}", response_model=ClienteOut)
def get_cliente(
    cliente_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    obj = db.get(Cliente, cliente_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return obj


@router.put("/{cliente_id}", response_model=ClienteOut)
def update_cliente(
    cliente_id: uuid.UUID,
    payload: ClienteUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_edit),
):
    obj = db.get(Cliente, cliente_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    vip_antes = obj.vip
    changes = payload.model_dump(exclude_none=True)
    for key, val in changes.items():
        setattr(obj, key, val)

    # Si se activa VIP y antes no lo era, crear suscripción de 1 mes
    if not vip_antes and obj.vip:
        now = datetime.now(timezone.utc)
        db.add(Suscripcion(
            cliente_id=obj.id,
            inicio=now,
            fin=now + relativedelta(months=1),
            activa=True,
        ))
        acumular_cuenta_vip(db)

    # Si se desactiva VIP, desactivar todas sus suscripciones activas
    if vip_antes and not obj.vip:
        db.query(Suscripcion).filter(
            Suscripcion.cliente_id == obj.id,
            Suscripcion.activa == True,
        ).update({"activa": False}, synchronize_session=False)

    _audit(db, user, "UPDATE", str(cliente_id), changes)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        if "codigo_vip" in str(e.orig):
            raise HTTPException(status_code=409, detail="El código VIP ya está en uso por otro cliente")
        raise HTTPException(status_code=409, detail="Conflicto de datos: valor duplicado")
    db.refresh(obj)
    return obj


@router.delete("/{cliente_id}", status_code=204)
def delete_cliente(
    cliente_id: uuid.UUID,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    obj = db.get(Cliente, cliente_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    _audit(db, user, "DELETE", str(cliente_id), {"nombre": obj.nombre, "celular": obj.celular})
    db.delete(obj)
    db.commit()
