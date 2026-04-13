from calendar import monthrange
from collections import Counter
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_platform_user
from app.database import get_db
from app.models.cliente import Cliente
from app.models.loteria_resultado import LoteriaResultado
from app.models.numero_acierto import NumeroAcierto
from app.models.numbers_historic import NumberHistoric

router = APIRouter(prefix="/admin/dashboard", tags=["Admin Dashboard"])


class TopLoteria(BaseModel):
    loteria: str
    aciertos: int


class DashboardStats(BaseModel):
    mes: str                          # "YYYY-MM"
    # ── Totalizados (independientes del mes) ────────────────────────────────
    total_clientes: int
    clientes_vip: int
    # ── Filtrados por mes ───────────────────────────────────────────────────
    numeros_entregados: int
    total_aciertos: int
    efectividad_pct: float            # 0–100 redondeado a 1 decimal
    exactos: int
    directo_devuelto: int
    tres_orden: int
    tres_desorden: int
    clientes_con_aciertos: int
    numero_mas_frecuente: Optional[str]
    top_loterias: list[TopLoteria]
    # ── Ganadores por tipo de número (filtrados por mes) ───────────────────
    ganadores_vip: int
    ganadores_free: int
    pct_ganadores_vip: float          # % sobre clientes_con_aciertos
    pct_ganadores_free: float


@router.get("", response_model=DashboardStats)
def get_dashboard(
    mes: Optional[str] = Query(None, description="Mes en formato YYYY-MM, por defecto mes actual"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    # ── Resolve month range ──────────────────────────────────────────────────
    today = date.today()
    if mes:
        year, month = int(mes[:4]), int(mes[5:7])
    else:
        year, month = today.year, today.month

    mes_str = f"{year:04d}-{month:02d}"
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])

    # ── Total & VIP clients ──────────────────────────────────────────────────
    total_clientes = db.query(Cliente).count()
    clientes_vip = db.query(Cliente).filter(Cliente.vip.is_(True)).count()

    # ── Numbers delivered in month ───────────────────────────────────────────
    historics = (
        db.query(NumberHistoric)
        .filter(NumberHistoric.date >= first_day, NumberHistoric.date <= last_day)
        .all()
    )
    numeros_entregados = len(historics)
    historic_ids = [h.id for h in historics]

    # ── Aciertos in month ────────────────────────────────────────────────────
    if historic_ids:
        aciertos = (
            db.query(NumeroAcierto)
            .filter(NumeroAcierto.historic_id.in_(historic_ids))
            .all()
        )
    else:
        aciertos = []

    total_aciertos = len(aciertos)
    efectividad = round(total_aciertos / numeros_entregados * 100, 1) if numeros_entregados else 0.0

    exactos = sum(1 for a in aciertos if a.tipo == "exacto")
    directo_devuelto = sum(1 for a in aciertos if a.tipo == "directo_devuelto")
    tres_orden = sum(1 for a in aciertos if a.tipo == "tres_orden")
    tres_desorden = sum(1 for a in aciertos if a.tipo == "tres_desorden")

    # ── Distinct clients with aciertos ───────────────────────────────────────
    historic_ids_with_aciertos = {a.historic_id for a in aciertos}
    if historic_ids_with_aciertos:
        clientes_ids = (
            db.query(NumberHistoric.id_user)
            .filter(NumberHistoric.id.in_(historic_ids_with_aciertos))
            .distinct()
            .all()
        )
        clientes_con_aciertos = len(clientes_ids)
    else:
        clientes_con_aciertos = 0

    # ── Ganadores por tipo de número (vip / free) ─────────────────────────
    if historic_ids_with_aciertos:
        ganadores_vip_ids = (
            db.query(NumberHistoric.id_user)
            .filter(
                NumberHistoric.id.in_(historic_ids_with_aciertos),
                NumberHistoric.type == "vip",
            )
            .distinct()
            .all()
        )
        ganadores_free_ids = (
            db.query(NumberHistoric.id_user)
            .filter(
                NumberHistoric.id.in_(historic_ids_with_aciertos),
                NumberHistoric.type == "free",
            )
            .distinct()
            .all()
        )
        ganadores_vip = len(ganadores_vip_ids)
        ganadores_free = len(ganadores_free_ids)
    else:
        ganadores_vip = 0
        ganadores_free = 0

    base_pct = clientes_con_aciertos if clientes_con_aciertos else 1
    pct_ganadores_vip = round(ganadores_vip / base_pct * 100, 1)
    pct_ganadores_free = round(ganadores_free / base_pct * 100, 1)

    # ── Most frequent winning number ─────────────────────────────────────────
    numero_mas_frecuente: Optional[str] = None
    if historic_ids_with_aciertos:
        numeros = (
            db.query(NumberHistoric.number)
            .filter(NumberHistoric.id.in_(historic_ids_with_aciertos))
            .all()
        )
        counter = Counter(n.number for n in numeros)
        numero_mas_frecuente = counter.most_common(1)[0][0] if counter else None

    # ── Top 5 loterias ───────────────────────────────────────────────────────
    resultado_ids = [a.resultado_id for a in aciertos]
    top_loterias: list[TopLoteria] = []
    if resultado_ids:
        loteria_counter: Counter = Counter(a.resultado_id for a in aciertos)
        # Fetch names for top 5
        top5_ids = [rid for rid, _ in loteria_counter.most_common(5)]
        resultados = {
            r.id: r.loteria
            for r in db.query(LoteriaResultado).filter(LoteriaResultado.id.in_(top5_ids)).all()
        }
        top_loterias = [
            TopLoteria(loteria=resultados.get(rid, "—"), aciertos=cnt)
            for rid, cnt in loteria_counter.most_common(5)
            if rid in resultados
        ]

    return DashboardStats(
        mes=mes_str,
        total_clientes=total_clientes,
        clientes_vip=clientes_vip,
        numeros_entregados=numeros_entregados,
        total_aciertos=total_aciertos,
        efectividad_pct=efectividad,
        exactos=exactos,
        directo_devuelto=directo_devuelto,
        tres_orden=tres_orden,
        tres_desorden=tres_desorden,
        clientes_con_aciertos=clientes_con_aciertos,
        numero_mas_frecuente=numero_mas_frecuente,
        top_loterias=top_loterias,
        ganadores_vip=ganadores_vip,
        ganadores_free=ganadores_free,
        pct_ganadores_vip=pct_ganadores_vip,
        pct_ganadores_free=pct_ganadores_free,
    )
