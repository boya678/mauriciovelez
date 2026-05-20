"""Endpoints públicos de loterías — sin autenticación.

Rate-limiting: aplicado en el ingress de K8s (20 req/min por IP).
"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.loteria_resultado import LoteriaResultado

router = APIRouter(prefix="/public/loterias", tags=["Público - Loterías"])


class ResultadoPublicOut(BaseModel):
    fecha: date
    loteria: str
    slug: str
    resultado: str
    serie: str

    model_config = {"from_attributes": True}


@router.get("/resultados", response_model=list[ResultadoPublicOut])
def get_resultados_publicos(
    fecha: date = Query(..., description="Fecha en formato YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """
    Devuelve los resultados de loterías para la fecha indicada.
    Endpoint público — sin autenticación requerida.
    El consumo está limitado a 20 peticiones por minuto por IP a nivel de ingress.
    """
    rows = (
        db.query(LoteriaResultado)
        .filter(LoteriaResultado.fecha == fecha)
        .order_by(LoteriaResultado.loteria)
        .all()
    )
    return rows
