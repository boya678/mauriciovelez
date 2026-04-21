from calendar import monthrange
from collections import Counter
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_platform_user
from app.database import get_db
from app.models.cliente import Cliente
from app.models.loteria_resultado import LoteriaResultado
from app.models.numero_acierto import NumeroAcierto
from app.models.numbers_historic import NumberHistoric
from app.models.suscripcion import Suscripcion

router = APIRouter(prefix="/admin/dashboard", tags=["Admin Dashboard"])


class TopLoteria(BaseModel):
    loteria: str
    aciertos: int


COLOMBIA_TZ = ZoneInfo("America/Bogota")


class DashboardStats(BaseModel):
    mes: str                          # "YYYY-MM"
    # ── Totalizados (independientes del mes) ────────────────────────────────
    total_clientes: int
    clientes_vip: int
    clientes_activos: int
    clientes_inactivos: int
    # ── Filtrados por mes ───────────────────────────────────────────────────
    numeros_entregados: int
    total_aciertos: int
    efectividad_numerica_pct: float    # aciertos / numeros_entregados
    efectividad_personal_pct: float    # clientes que ganaron / clientes con números
    clientes_con_numeros: int
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
    # ── Suscripciones iniciadas en el mes ─────────────────────────────────
    suscripciones_iniciadas: int
    # ── Nuevos clientes registrados en el mes ───────────────────────────
    nuevos_clientes: int
    # ── % resultados con últimos 3 dígitos todos diferentes ────────────────
    pct_3digitos_diferentes: float
    total_resultados_mes: int
    resultados_3dif: int


@router.get("", response_model=DashboardStats)
def get_dashboard(
    mes: Optional[str] = Query(None, description="Mes en formato YYYY-MM, por defecto mes actual"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    # ── Resolve month range ──────────────────────────────────────────────────
    today = datetime.now(COLOMBIA_TZ).date()
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
    clientes_activos = db.query(Cliente).filter(Cliente.enabled.is_(True)).count()
    clientes_inactivos = total_clientes - clientes_activos

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
    efectividad_numerica = round(total_aciertos / numeros_entregados * 100, 1) if numeros_entregados else 0.0

    # ── Clientes distintos con números en el mes ─────────────────────────────
    clientes_con_numeros = len(set(h.id_user for h in historics))

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

    efectividad_personal = round(clientes_con_aciertos / clientes_con_numeros * 100, 1) if clientes_con_numeros else 0.0

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

    # ── Suscripciones iniciadas en el mes ─────────────────────────────────
    first_dt = datetime(year, month, 1, tzinfo=COLOMBIA_TZ)
    last_dt = datetime(year, month, monthrange(year, month)[1], 23, 59, 59, tzinfo=COLOMBIA_TZ)
    suscripciones_iniciadas = (
        db.query(Suscripcion)
        .filter(Suscripcion.inicio >= first_dt, Suscripcion.inicio <= last_dt)
        .count()
    )

    # ── Nuevos clientes registrados en el mes ───────────────────────────
    nuevos_clientes = (
        db.query(Cliente)
        .filter(Cliente.created_at >= first_dt, Cliente.created_at <= last_dt)
        .count()
    )

    # ── % resultados del mes con últimos 3 dígitos todos diferentes ─────────
    resultados_mes = (
        db.query(LoteriaResultado.resultado)
        .filter(LoteriaResultado.fecha >= first_day, LoteriaResultado.fecha <= last_day)
        .all()
    )
    total_res = len(resultados_mes)
    if total_res:
        def _ultimos3(r: str) -> str:
            digits = ''.join(c for c in r if c.isdigit())
            return digits[-3:] if len(digits) >= 3 else ''
        todos_diferentes = sum(
            1 for (r,) in resultados_mes
            if (u3 := _ultimos3(r)) and len(set(u3)) == 3
        )
        pct_3digitos_diferentes = round(todos_diferentes / total_res * 100, 1)
    else:
        todos_diferentes = 0
        pct_3digitos_diferentes = 0.0

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
        clientes_activos=clientes_activos,
        clientes_inactivos=clientes_inactivos,
        numeros_entregados=numeros_entregados,
        total_aciertos=total_aciertos,
        efectividad_numerica_pct=efectividad_numerica,
        efectividad_personal_pct=efectividad_personal,
        clientes_con_numeros=clientes_con_numeros,
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
        suscripciones_iniciadas=suscripciones_iniciadas,
        nuevos_clientes=nuevos_clientes,
        pct_3digitos_diferentes=pct_3digitos_diferentes,
        total_resultados_mes=total_res,
        resultados_3dif=todos_diferentes,
    )
