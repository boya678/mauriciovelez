import io
from datetime import date, timedelta
from typing import Optional

import openpyxl
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_platform_user
from app.database import get_db
from app.models.cliente import Cliente
from app.models.numero_acierto import NumeroAcierto
from app.models.numbers_historic import NumberHistoric
from app.models.numbers_users import NumberUser

router = APIRouter(prefix="/admin/historico", tags=["Admin Histórico"])


# ── Schemas ──────────────────────────────────────────────────────────────────────

class HistoricoRow(BaseModel):
    id: int
    fecha: date
    nombre: str
    celular: str
    cc: Optional[str]
    numero: str
    aciertos: int = 0
    vip: bool = False


class PaginatedHistorico(BaseModel):
    total: int
    page: int
    size: int
    items: list[HistoricoRow]


# ── Helper query (join historic + clientes) ───────────────────────────────────────

def _build_query(db: Session, desde: date, hasta: date, solo_ganadores: bool = False, filtro_vip: Optional[str] = None):
    q = (
        db.query(
            NumberHistoric.id,
            NumberHistoric.date.label("fecha"),
            Cliente.nombre,
            Cliente.celular,
            Cliente.cc,
            NumberHistoric.number.label("numero"),
            Cliente.vip,
        )
        .join(Cliente, NumberHistoric.id_user == Cliente.id)
        .filter(NumberHistoric.date >= desde, NumberHistoric.date <= hasta)
        .order_by(NumberHistoric.date.desc(), Cliente.nombre)
    )
    if solo_ganadores:
        q = q.filter(
            db.query(NumeroAcierto)
            .filter(NumeroAcierto.historic_id == NumberHistoric.id)
            .exists()
        )
    if filtro_vip == "vip":
        q = q.filter(Cliente.vip == True)
    elif filtro_vip == "no_vip":
        q = q.filter(Cliente.vip == False)
    return q


def _defaults(desde, hasta):
    ayer = date.today() - timedelta(days=1)
    return desde or ayer, hasta or ayer


# ── Endpoints ────────────────────────────────────────────────────────────────────

@router.get("", response_model=PaginatedHistorico)
def list_historico(
    desde: Optional[date] = Query(None),
    hasta: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    solo_ganadores: bool = Query(False),
    filtro_vip: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    _desde, _hasta = _defaults(desde, hasta)
    q = _build_query(db, _desde, _hasta, solo_ganadores, filtro_vip)
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    items = [
        HistoricoRow(
            id=r.id, fecha=r.fecha, nombre=r.nombre,
            celular=r.celular, cc=r.cc, numero=r.numero,
            aciertos=db.query(NumeroAcierto).filter(NumeroAcierto.historic_id == r.id).count(),
            vip=r.vip,
        )
        for r in rows
    ]
    return PaginatedHistorico(total=total, page=page, size=size, items=items)


@router.get("/export")
def export_historico(
    desde: Optional[date] = Query(None),
    hasta: Optional[date] = Query(None),
    solo_ganadores: bool = Query(False),
    filtro_vip: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    _desde, _hasta = _defaults(desde, hasta)

    # Query extendida: incluye VIP del cliente y tipo del número asignado
    base_q = (
        db.query(
            NumberHistoric.id,
            NumberHistoric.date.label("fecha"),
            Cliente.nombre,
            Cliente.celular,
            Cliente.cc,
            NumberHistoric.number.label("numero"),
            Cliente.vip,
            NumberUser.type.label("tipo_numero"),
        )
        .join(Cliente, NumberHistoric.id_user == Cliente.id)
        .outerjoin(
            NumberUser,
            (NumberUser.id_user == NumberHistoric.id_user)
            & (NumberUser.number == NumberHistoric.number)
            & (NumberUser.date_assigned <= NumberHistoric.date)
            & (NumberUser.valid_until >= NumberHistoric.date),
        )
        .filter(NumberHistoric.date >= _desde, NumberHistoric.date <= _hasta)
        .order_by(NumberHistoric.date.desc(), Cliente.nombre)
    )
    if solo_ganadores:
        base_q = base_q.filter(
            db.query(NumeroAcierto)
            .filter(NumeroAcierto.historic_id == NumberHistoric.id)
            .exists()
        )
    if filtro_vip == 'vip':
        base_q = base_q.filter(Cliente.vip == True)
    elif filtro_vip == 'no_vip':
        base_q = base_q.filter(Cliente.vip == False)
    rows = base_q.all()

    # First pass: collect aciertos per row and determine max count for dynamic columns
    rows_data: list[tuple] = []
    max_aciertos = 0
    for r in rows:
        aciertos = (
            db.query(NumeroAcierto)
            .filter(NumeroAcierto.historic_id == r.id)
            .all()
        )
        rows_data.append((r, aciertos))
        if len(aciertos) > max_aciertos:
            max_aciertos = len(aciertos)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Histórico"

    # Header: columnas base + VIP cliente + tipo número + aciertos dinámicos
    header = ["Fecha", "Nombre", "Celular", "CC", "Número", "VIP Cliente", "Tipo Número"]
    for i in range(1, max_aciertos + 1):
        header += [f"Tipo {i}", f"Lotería {i}", f"Resultado {i}"]
    ws.append(header)

    for r, aciertos in rows_data:
        row: list = [
            str(r.fecha),
            r.nombre,
            r.celular,
            r.cc or "",
            r.numero,
            "Sí" if r.vip else "No",
            r.tipo_numero or "—",
        ]
        for a in aciertos:
            row += [a.tipo, a.resultado.loteria, a.resultado.resultado]
        row += ["", "", ""] * (max_aciertos - len(aciertos))
        ws.append(row)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    fname = f"historico_{_desde}_{_hasta}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )
