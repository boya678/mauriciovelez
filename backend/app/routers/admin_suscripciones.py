import uuid
from datetime import datetime, timezone
from typing import Optional

import openpyxl
import io
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_platform_user, require_admin
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.suscripcion import Suscripcion
from app.models.cuenta_vip import acumular_cuenta_vip
from app.models.cliente import Cliente
from app.core import scheduler as _scheduler_module

router = APIRouter(prefix="/admin/suscripciones", tags=["Admin Suscripciones"])


# ── Schemas ──────────────────────────────────────────────────────────────────────

class SuscripcionOut(BaseModel):
    id: uuid.UUID
    cliente_id: uuid.UUID
    nombre: str
    celular: str
    inicio: datetime
    fin: datetime
    activa: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedSuscripciones(BaseModel):
    total: int
    page: int
    size: int
    items: list[SuscripcionOut]


# ── Endpoints ────────────────────────────────────────────────────────────────────

@router.get("", response_model=PaginatedSuscripciones)
def list_suscripciones(
    q: Optional[str] = Query(None, description="Buscar por nombre o celular"),
    solo_activas: bool = Query(False),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    query = (
        db.query(Suscripcion, Cliente.nombre, Cliente.celular)
        .join(Cliente, Suscripcion.cliente_id == Cliente.id)
    )
    if q:
        like = f"%{q}%"
        query = query.filter(
            Cliente.nombre.ilike(like) | Cliente.celular.ilike(like)
        )
    if solo_activas:
        now = datetime.now(timezone.utc)
        query = query.filter(Suscripcion.activa == True, Suscripcion.fin >= now)

    total = query.count()
    rows = query.order_by(Suscripcion.fin.desc()).offset((page - 1) * size).limit(size).all()

    items = [
        SuscripcionOut(
            id=s.id,
            cliente_id=s.cliente_id,
            nombre=nombre,
            celular=celular,
            inicio=s.inicio,
            fin=s.fin,
            activa=s.activa,
            created_at=s.created_at,
        )
        for s, nombre, celular in rows
    ]
    return PaginatedSuscripciones(total=total, page=page, size=size, items=items)


@router.post("/{suscripcion_id}/renovar", response_model=SuscripcionOut)
def renovar(
    suscripcion_id: uuid.UUID,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    sus = db.get(Suscripcion, suscripcion_id)
    if sus is None:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")

    cliente = db.get(Cliente, sus.cliente_id)
    now = datetime.now(timezone.utc)

    # 1. Inactivar TODAS las suscripciones existentes del cliente
    db.query(Suscripcion).filter(
        Suscripcion.cliente_id == sus.cliente_id
    ).update({"activa": False}, synchronize_session="fetch")

    # 2. Crear nueva suscripción desde ahora + 1 mes
    nueva = Suscripcion(
        cliente_id=sus.cliente_id,
        inicio=now,
        fin=now + relativedelta(months=1),
        activa=True,
    )
    db.add(nueva)

    # 3. Asegurar que el cliente quede marcado como VIP
    if cliente and not cliente.vip:
        cliente.vip = True

    acumular_cuenta_vip(db)

    db.add(AuditLog(
        platform_user_id=user.id,
        usuario=user.usuario,
        action="RENOVAR",
        entity="suscripciones",
        entity_id=str(suscripcion_id),
        detail={
            "cliente_id": str(sus.cliente_id),
            "nombre": cliente.nombre if cliente else "",
            "nueva_inicio": now.isoformat(),
            "nueva_fin": (now + relativedelta(months=1)).isoformat(),
        },
    ))

    db.commit()
    db.refresh(nueva)

    return SuscripcionOut(
        id=nueva.id,
        cliente_id=nueva.cliente_id,
        nombre=cliente.nombre if cliente else "",
        celular=cliente.celular if cliente else "",
        inicio=nueva.inicio,
        fin=nueva.fin,
        activa=nueva.activa,
        created_at=nueva.created_at,
    )


@router.get("/export")
def export_suscripciones(
    q: Optional[str] = Query(None),
    solo_activas: bool = Query(False),
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    query = (
        db.query(Suscripcion, Cliente.nombre, Cliente.celular)
        .join(Cliente, Suscripcion.cliente_id == Cliente.id)
    )
    if q:
        like = f"%{q}%"
        query = query.filter(
            Cliente.nombre.ilike(like) | Cliente.celular.ilike(like)
        )
    if solo_activas:
        now = datetime.now(timezone.utc)
        query = query.filter(Suscripcion.activa == True, Suscripcion.fin >= now)

    rows = query.order_by(Suscripcion.fin.desc()).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Suscripciones"
    ws.append(["Nombre", "Celular", "Inicio", "Fin", "Activa"])
    for s, nombre, celular in rows:
        ws.append([
            nombre,
            celular,
            s.inicio.strftime("%Y-%m-%d"),
            s.fin.strftime("%Y-%m-%d"),
            "Sí" if s.activa else "No",
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=suscripciones.xlsx"},
    )


@router.post("/run-vip-check", status_code=200)
def run_vip_check(_user=Depends(require_admin)):
    """Ejecuta manualmente el proceso de desactivación de VIPs vencidos."""
    _scheduler_module._desactivar_vip_vencidos()
    return {"ok": True, "mensaje": "Verificación VIP ejecutada"}
