from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_platform_user, require_admin
from app.core import scheduler as _scheduler_module
from app.database import get_db
from app.models.loteria_resultado import LoteriaResultado
from app.models.numero_acierto import NumeroAcierto
from app.models.numbers_historic import NumberHistoric

router = APIRouter(prefix="/admin/loterias", tags=["Admin Loterias"])


# ── Schemas ──────────────────────────────────────────────────────────────────────

class ResultadoOut(BaseModel):
    id: str
    fecha: date
    loteria: str
    slug: str
    resultado: str
    serie: str

    model_config = {"from_attributes": True}


class AciertoOut(BaseModel):
    id: str
    historic_id: int
    tipo: str
    numero: str
    loteria: str
    resultado: str
    fecha: date

    model_config = {"from_attributes": True}


# ── Endpoints ────────────────────────────────────────────────────────────────────

@router.post("/run", status_code=200)
def run_manual(
    fecha: Optional[date] = Query(None, description="Fecha YYYY-MM-DD (default: hoy Colombia)"),
    _user=Depends(require_admin),
):
    """Ejecuta manualmente el proceso de loterias para una fecha."""
    _scheduler_module._procesar_loterias(fecha)
    return {"ok": True, "mensaje": f"Procesado para {fecha or 'hoy (Colombia)'}"}


@router.get("/resultados", response_model=list[ResultadoOut])
def get_resultados(
    fecha: date = Query(..., description="Fecha YYYY-MM-DD"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    rows = (
        db.query(LoteriaResultado)
        .filter(LoteriaResultado.fecha == fecha)
        .order_by(LoteriaResultado.loteria)
        .all()
    )
    return [ResultadoOut(
        id=str(r.id), fecha=r.fecha, loteria=r.loteria,
        slug=r.slug, resultado=r.resultado, serie=r.serie,
    ) for r in rows]


@router.get("/aciertos/{historic_id}", response_model=list[AciertoOut])
def get_aciertos(
    historic_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    """Devuelve los aciertos de un registro histórico dado."""
    h = db.get(NumberHistoric, historic_id)
    if h is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    rows = (
        db.query(NumeroAcierto)
        .filter(NumeroAcierto.historic_id == historic_id)
        .all()
    )
    result = []
    for a in rows:
        r = a.resultado
        result.append(AciertoOut(
            id=str(a.id),
            historic_id=a.historic_id,
            tipo=a.tipo,
            numero=h.number,
            loteria=r.loteria,
            resultado=r.resultado,
            fecha=r.fecha,
        ))
    return result
