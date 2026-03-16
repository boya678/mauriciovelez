import random
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models.cliente import Cliente
from app.models.loteria_resultado import LoteriaResultado
from app.models.numero_acierto import NumeroAcierto
from app.models.numbers import Number
from app.models.numbers_historic import NumberHistoric
from app.models.numbers_users import NumberUser

router = APIRouter(prefix="/numerologia", tags=["Numerologia"])

VIGENCIA_FREE = 10  # días
VIGENCIA_VIP = 3   # días


# ─── helpers ──────────────────────────────────────────────────────────────────

def _apply_method(number: str) -> str:
    """Permutación Mauricio Vélez: pos[0]+pos[3]+pos[2]+pos[1]."""
    return number[0] + number[3] + number[2] + number[1]


def _assign_number(db: Session, id_user, num_type: str, validity_days: int) -> NumberUser:
    """
    Asigna un número del pool al usuario para el tipo dado.
    - Borra la asignación anterior del mismo tipo.
    - Si el pool está vacío, resetea todos a disponibles.
    - Prefija un dígito aleatorio 0-9 al número de 3 cifras.
    - Registra en numbers_historic.
    """
    # Eliminar asignación anterior del mismo tipo
    db.execute(
        delete(NumberUser).where(
            NumberUser.id_user == id_user,
            NumberUser.type == num_type,
        )
    )
    db.flush()

    # Obtener números disponibles
    available = db.execute(
        select(Number).where(Number.assigned.is_(False))
    ).scalars().all()

    if not available:
        # Resetear pool completo
        db.execute(update(Number).values(assigned=False))
        db.flush()
        available = db.execute(
            select(Number).where(Number.assigned.is_(False))
        ).scalars().all()

    selected = random.choice(available)
    prefix = str(random.randint(0, 9))
    final_number = prefix + selected.number  # 4 dígitos: x + 3 cifras

    # Marcar el número del pool como ocupado
    selected.assigned = True

    today = date.today()

    assignment = NumberUser(
        number=final_number,
        id_user=id_user,
        date_assigned=today,
        valid_until=today + timedelta(days=validity_days),
        type=num_type,
    )
    db.add(assignment)

    # Histórico
    db.add(NumberHistoric(number=final_number, id_user=id_user, date=today))

    db.flush()
    return assignment


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

    # ── Número gratuito (todos los usuarios) ──────────────────
    free_row = db.execute(
        select(NumberUser).where(
            NumberUser.id_user == current_user.id,
            NumberUser.type == "free",
        )
    ).scalar_one_or_none()

    if free_row is None or free_row.valid_until < today:
        free_row = _assign_number(db, current_user.id, "free", VIGENCIA_FREE)

    result: dict = {
        "nombre": current_user.nombre,
        "es_vip": current_user.vip,
        "numero_libre": _serialize(free_row),
    }

    # ── Número VIP (solo usuarios VIP) ───────────────────────
    if current_user.vip:
        vip_row = db.execute(
            select(NumberUser).where(
                NumberUser.id_user == current_user.id,
                NumberUser.type == "vip",
            )
        ).scalar_one_or_none()

        if vip_row is None or vip_row.valid_until < today:
            vip_row = _assign_number(db, current_user.id, "vip", VIGENCIA_VIP)

        result["numero_vip"] = _serialize(vip_row)

    db.commit()
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
