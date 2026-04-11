import random
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models.cliente import Cliente
from app.models.loteria_resultado import LoteriaResultado
from app.models.numero_acierto import NumeroAcierto
from app.models.numbers_historic import NumberHistoric
from app.models.numbers_users import NumberUser
from app.services.numbers import VIGENCIA_FREE, VIGENCIA_VIP

router = APIRouter(prefix="/numerologia", tags=["Numerologia"])


# ─── helpers ──────────────────────────────────────────────────────────────────

def _apply_method(number: str) -> str:
    """Permutación Mauricio Vélez: pos[0]+pos[3]+pos[2]+pos[1]."""
    return number[0] + number[3] + number[2] + number[1]


def _serialize(assignment: NumberUser) -> dict:
    today = date.today()
    dias = max(0, (assignment.valid_until - today).days)
    return {
        "numero": assignment.number,
        "numero_metodo": _apply_method(assignment.number),
        "fecha_asignacion": assignment.date_assigned.isoformat(),
        "vigencia_hasta": assignment.valid_until.isoformat(),
        "dias_restantes": dias,
    }


# ─── endpoint ─────────────────────────────────────────────────────────────────

@router.get("/mis-numeros")
def get_mis_numeros(
    current_user: Annotated[Cliente, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    today = date.today()

    # ── Número gratuito ───────────────────────────────────────
    free_row = db.execute(
        select(NumberUser).where(
            NumberUser.id_user == current_user.id,
            NumberUser.type == "free",
        )
    ).scalar_one_or_none()

    result: dict = {
        "nombre": current_user.nombre,
        "es_vip": current_user.vip,
        "numero_libre": _serialize(free_row) if free_row else None,
    }

    # ── Número VIP (solo usuarios VIP) ───────────────────────
    if current_user.vip:
        vip_row = db.execute(
            select(NumberUser).where(
                NumberUser.id_user == current_user.id,
                NumberUser.type == "vip",
            )
        ).scalar_one_or_none()

        result["numero_vip"] = _serialize(vip_row) if vip_row else None

    return result


@router.get("/mis-aciertos")
def get_mis_aciertos(
    current_user: Annotated[Cliente, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Devuelve los aciertos del cliente autenticado en los últimos 2 meses."""
    cutoff = date.today() - timedelta(days=60)

    historicos = (
        db.query(NumberHistoric)
        .filter(NumberHistoric.id_user == current_user.id, NumberHistoric.date >= cutoff)
        .order_by(NumberHistoric.date.desc())
        .all()
    )

    result = []
    for h in historicos:
        aciertos = (
            db.query(NumeroAcierto)
            .filter(NumeroAcierto.historic_id == h.id)
            .all()
        )
        for a in aciertos:
            r = a.resultado
            result.append({
                "numero": h.number,
                "fecha": h.date.isoformat(),
                "tipo": a.tipo,
                "loteria": r.loteria,
                "resultado": r.resultado,
            })

    result.sort(key=lambda x: x["fecha"], reverse=True)
    return result
