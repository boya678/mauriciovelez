from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_platform_user
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
    total_aciertos: int = 0

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
    # Contar aciertos por resultado
    counts = dict(
        db.query(NumeroAcierto.resultado_id, func.count(NumeroAcierto.id))
        .join(LoteriaResultado, NumeroAcierto.resultado_id == LoteriaResultado.id)
        .filter(LoteriaResultado.fecha == fecha)
        .group_by(NumeroAcierto.resultado_id)
        .all()
    )
    return [ResultadoOut(
        id=str(r.id), fecha=r.fecha, loteria=r.loteria,
        slug=r.slug, resultado=r.resultado, serie=r.serie,
        total_aciertos=counts.get(r.id, 0),
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
