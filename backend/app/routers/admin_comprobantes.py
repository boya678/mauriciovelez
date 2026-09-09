import io
import math
import uuid
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.admin_security import require_admin
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.comprobante_vip import ComprobanteVip

router = APIRouter(prefix="/admin/comprobantes", tags=["Admin Comprobantes"])

COL_TZ = ZoneInfo("America/Bogota")
PAGE_SIZE = 50


class ComprobanteOut(BaseModel):
    id: uuid.UUID
    comprobante_num: str
    celular: str
    monto: float
    descripcion: str
    message_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class PagedComprobantes(BaseModel):
    total: int
    page: int
    pages: int
    items: list[ComprobanteOut]


def _rango_default() -> tuple[date, date]:
    """Sin filtro explícito, limita a los últimos 30 días para evitar escanear toda la tabla."""
    hoy = datetime.now(COL_TZ).date()
    return hoy - timedelta(days=30), hoy


def _build_query(db: Session, fecha_inicio: Optional[date], fecha_fin: Optional[date], comprobante_num: Optional[str]):
    q = db.query(ComprobanteVip)
    fecha_col = func.date(func.timezone("America/Bogota", ComprobanteVip.created_at))
    if fecha_inicio:
        q = q.filter(fecha_col >= fecha_inicio)
    if fecha_fin:
        q = q.filter(fecha_col <= fecha_fin)
    if comprobante_num:
        q = q.filter(ComprobanteVip.comprobante_num.ilike(f"%{comprobante_num}%"))
    return q


@router.get("/exportar")
def exportar_comprobantes(
    fecha_inicio: Optional[date] = Query(default=None),
    fecha_fin: Optional[date] = Query(default=None),
    comprobante_num: Optional[str] = Query(default=None),
    _user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    if fecha_inicio is None and fecha_fin is None:
        fecha_inicio, fecha_fin = _rango_default()

    items = (
        _build_query(db, fecha_inicio, fecha_fin, comprobante_num)
        .order_by(ComprobanteVip.created_at.desc())
        .all()
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Comprobantes VIP"
    ws.append(["Fecha", "Nro. Comprobante", "Celular", "Monto", "Descripción", "Image Hash", "Message ID"])
    for c in items:
        fecha_col = datetime.fromisoformat(str(c.created_at)).astimezone(
            ZoneInfo("America/Bogota")
        ).strftime("%d/%m/%Y %H:%M")
        ws.append([
            fecha_col,
            c.comprobante_num,
            c.celular,
            float(c.monto),
            c.descripcion,
            c.image_hash or "",
            str(c.message_id),
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"comprobantes_{fecha_inicio}_a_{fecha_fin}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("", response_model=PagedComprobantes)
def list_comprobantes(
    fecha_inicio: Optional[date] = Query(default=None, description="Fecha inicio (YYYY-MM-DD)"),
    fecha_fin: Optional[date] = Query(default=None, description="Fecha fin (YYYY-MM-DD)"),
    comprobante_num: Optional[str] = Query(default=None, description="Filtrar por número de comprobante (parcial)"),
    page: int = Query(default=1, ge=1),
    _user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    if fecha_inicio is None and fecha_fin is None:
        fecha_inicio, fecha_fin = _rango_default()

    q = _build_query(db, fecha_inicio, fecha_fin, comprobante_num)
    total = q.count()
    items = (
        q.order_by(ComprobanteVip.created_at.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )
    pages = max(1, math.ceil(total / PAGE_SIZE))
    return PagedComprobantes(total=total, page=page, pages=pages, items=items)


@router.delete("/{id}", status_code=204)
def delete_comprobante(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    obj = db.execute(
        select(ComprobanteVip).where(ComprobanteVip.id == id)
    ).scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")
    db.add(AuditLog(
        platform_user_id=_user.id,
        usuario=_user.usuario,
        action="DELETE",
        entity="comprobantes_vip",
        entity_id=str(id),
        detail={"comprobante_num": obj.comprobante_num, "celular": obj.celular, "monto": float(obj.monto)},
    ))
    db.delete(obj)
    db.commit()
