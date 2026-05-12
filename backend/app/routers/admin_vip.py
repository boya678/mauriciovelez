import io
from datetime import datetime, timezone
from typing import Optional

import openpyxl
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import cast, Date, func
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_platform_user
from app.database import get_db
from app.models.cliente import Cliente
from app.models.numero_acierto import NumeroAcierto
from app.models.numbers_historic import NumberHistoric
from app.models.suscripcion import Suscripcion

router = APIRouter(prefix="/admin/vip", tags=["Admin VIP"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class VipClienteRow(BaseModel):
    id: str
    nombre: str
    celular: str
    codigo_vip: Optional[str]
    total_suscripciones: int
    veces_gano: int
    suscripcion_activa: bool
    cliente_habilitado: bool


class PaginatedVip(BaseModel):
    total: int
    page: int
    size: int
    items: list[VipClienteRow]


# ── Query base ────────────────────────────────────────────────────────────────

def _base_query(db: Session):
    sq_subs = (
        db.query(
            Suscripcion.cliente_id.label("cliente_id"),
            func.count(Suscripcion.id).label("total_subs"),
        )
        .group_by(Suscripcion.cliente_id)
        .subquery()
    )

    sq_aciertos = (
        db.query(
            NumberHistoric.id_user.label("cliente_id"),
            func.count(NumeroAcierto.id).label("ganos"),
        )
        .join(NumeroAcierto, NumeroAcierto.historic_id == NumberHistoric.id)
        .group_by(NumberHistoric.id_user)
        .subquery()
    )

    return (
        db.query(
            Cliente.id,
            Cliente.nombre,
            Cliente.celular,
            Cliente.codigo_vip,
            Cliente.enabled,
            func.coalesce(sq_subs.c.total_subs, 0).label("total_subs"),
            func.coalesce(sq_aciertos.c.ganos, 0).label("ganos"),
        )
        .outerjoin(sq_subs, sq_subs.c.cliente_id == Cliente.id)
        .outerjoin(sq_aciertos, sq_aciertos.c.cliente_id == Cliente.id)
        .filter(Cliente.tipo_cliente == 1, Cliente.codigo_vip.isnot(None))
        .order_by(Cliente.nombre)
    )


def _apply_filters(q, db: Session, solo_ganadores: bool, solo_activos: bool, solo_inactivos: bool):
    hoy = datetime.now(timezone.utc).date()

    if solo_ganadores:
        sq_gan = (
            db.query(NumberHistoric.id_user)
            .join(NumeroAcierto, NumeroAcierto.historic_id == NumberHistoric.id)
            .distinct()
            .subquery()
        )
        q = q.filter(Cliente.id.in_(sq_gan))

    if solo_activos:
        sq_activa = (
            db.query(Suscripcion.cliente_id)
            .filter(
                Suscripcion.activa == True,
                cast(Suscripcion.fin, Date) >= hoy,
            )
            .distinct()
            .subquery()
        )
        q = q.filter(Cliente.id.in_(sq_activa))

    if solo_inactivos:
        sq_activa_ids = (
            db.query(Suscripcion.cliente_id)
            .filter(
                Suscripcion.activa == True,
                cast(Suscripcion.fin, Date) >= hoy,
            )
            .distinct()
            .subquery()
        )
        q = q.filter(Cliente.id.notin_(sq_activa_ids))

    return q, hoy


def _to_items(rows, db: Session, hoy) -> list[VipClienteRow]:
    if not rows:
        return []
    activas_set = {
        str(s.cliente_id)
        for s in db.query(Suscripcion.cliente_id)
        .filter(
            Suscripcion.cliente_id.in_([r.id for r in rows]),
            Suscripcion.activa == True,
            cast(Suscripcion.fin, Date) >= hoy,
        )
        .distinct()
        .all()
    }
    return [
        VipClienteRow(
            id=str(r.id),
            nombre=r.nombre,
            celular=r.celular,
            codigo_vip=r.codigo_vip,
            total_suscripciones=r.total_subs,
            veces_gano=r.ganos,
            suscripcion_activa=str(r.id) in activas_set,
            cliente_habilitado=r.enabled,
        )
        for r in rows
    ]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=PaginatedVip)
def list_vip(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    solo_ganadores: bool = Query(False),
    solo_activos: bool = Query(False),
    solo_inactivos: bool = Query(False),
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    q = _base_query(db)
    q, hoy = _apply_filters(q, db, solo_ganadores, solo_activos, solo_inactivos)
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    return PaginatedVip(total=total, page=page, size=size, items=_to_items(rows, db, hoy))


@router.get("/export")
def export_vip(
    solo_ganadores: bool = Query(False),
    solo_activos: bool = Query(False),
    solo_inactivos: bool = Query(False),
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    q = _base_query(db)
    q, hoy = _apply_filters(q, db, solo_ganadores, solo_activos, solo_inactivos)
    rows = q.all()
    items = _to_items(rows, db, hoy)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "VIP"
    ws.append(["Nombre", "Celular", "Código VIP", "Suscripciones", "Veces ganó", "Suscripción activa", "Cliente habilitado"])
    for it in items:
        ws.append([
            it.nombre, it.celular, it.codigo_vip or "",
            it.total_suscripciones, it.veces_gano,
            "Sí" if it.suscripcion_activa else "No",
            "Sí" if it.cliente_habilitado else "No",
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=vip_{hoy}.xlsx"},
    )
