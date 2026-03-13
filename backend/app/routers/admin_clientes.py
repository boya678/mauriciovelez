import csv
import io
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_platform_user, require_admin, require_edit
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.cliente import Cliente

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

    model_config = {"from_attributes": True}


class ClienteUpdate(BaseModel):
    nombre: Optional[str] = None
    correo: Optional[str] = None
    cc: Optional[str] = None
    saldo: Optional[float] = None
    vip: Optional[bool] = None


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
    items = query.order_by(Cliente.nombre).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Nombre", "Celular", "CC", "Correo", "Saldo", "VIP"])
    for c in items:
        writer.writerow([
            c.nombre, c.celular, c.cc or "", c.correo or "",
            c.saldo, "Sí" if c.vip else "No",
        ])

    # BOM UTF-8 para que Excel abra correctamente tildes y ñ
    content = "\ufeff" + output.getvalue()

    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=clientes.csv"},
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
    changes = payload.model_dump(exclude_none=True)
    for key, val in changes.items():
        setattr(obj, key, val)
    _audit(db, user, "UPDATE", str(cliente_id), changes)
    db.commit()
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
