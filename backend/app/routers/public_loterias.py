"""Endpoints públicos de loterías — sin autenticación.

Rate-limiting: aplicado en el ingress de K8s (20 req/min por IP).
"""
import json
import logging
from datetime import date, datetime, timedelta

import redis
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.database import get_db
from app.models.loteria_resultado import LoteriaResultado
from app.models.numero_acierto import NumeroAcierto

logger = logging.getLogger(__name__)

COL_TZ = ZoneInfo("America/Bogota")

CACHE_TTL_PAST  = 600   # 10 min para fechas pasadas
CACHE_TTL_TODAY = 60    # 60 s para hoy (los aciertos se registran con delay)
CACHE_TTL_WEEK  = 3600  # 1 h para el resumen semanal
CACHE_TTL_MES   = 300   # 5 min para el mes actual
CACHE_TTL_ANIO  = 1800  # 30 min para el año actual

router = APIRouter(prefix="/public/loterias", tags=["Público - Loterías"])

_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


class ResultadoPublicOut(BaseModel):
    fecha: date
    loteria: str
    slug: str
    resultado: str
    total_aciertos: int = 0

    model_config = {"from_attributes": True}


class GanadoresSemanaOut(BaseModel):
    total_ganadores: int
    dias: int


class GanadoresStatsOut(BaseModel):
    hoy: int
    mes: int
    anio: int


@router.get("/resultados", response_model=list[ResultadoPublicOut])
def get_resultados_publicos(
    fecha: date = Query(..., description="Fecha en formato YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """
    Devuelve los resultados de loterías para la fecha indicada, incluido el total
    de aciertos (ganadores) por cada resultado.
    Hoy usa TTL 60s; fechas pasadas 600s.
    """
    cache_key = f"public:loterias:{fecha}"
    ttl = CACHE_TTL_TODAY if fecha == datetime.now(COL_TZ).date() else CACHE_TTL_PAST

    # ── Intentar cache ─────────────────────────────────────────────────────────
    try:
        cached = _get_redis().get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        logger.warning("Redis no disponible — consultando DB directamente")

    # ── Consulta DB ────────────────────────────────────────────────────────────
    rows = (
        db.query(LoteriaResultado)
        .filter(LoteriaResultado.fecha == fecha)
        .order_by(LoteriaResultado.loteria)
        .all()
    )
    counts = dict(
        db.query(NumeroAcierto.resultado_id, func.count(NumeroAcierto.id))
        .join(LoteriaResultado, NumeroAcierto.resultado_id == LoteriaResultado.id)
        .filter(LoteriaResultado.fecha == fecha)
        .group_by(NumeroAcierto.resultado_id)
        .all()
    )
    result = [
        ResultadoPublicOut(
            fecha=r.fecha,
            loteria=r.loteria,
            slug=r.slug,
            resultado=r.resultado,
            total_aciertos=counts.get(r.id, 0),
        )
        for r in rows
    ]

    # ── Guardar en cache ───────────────────────────────────────────────────────
    try:
        payload = json.dumps([r.model_dump(mode="json") for r in result])
        _get_redis().setex(cache_key, ttl, payload)
    except Exception:
        logger.warning("Redis no disponible — respuesta no cacheada")

    return result


@router.get("/stats/semana", response_model=GanadoresSemanaOut)
def get_ganadores_semana(db: Session = Depends(get_db)):
    """
    Suma de aciertos (ganadores con el software) en los últimos 7 días.
    Cacheado 1 h en Redis.
    """
    cache_key = "public:loterias:semana"

    try:
        cached = _get_redis().get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        logger.warning("Redis no disponible — consultando DB directamente")

    desde = datetime.now(COL_TZ).date() - timedelta(days=6)
    total: int = (
        db.query(func.count(NumeroAcierto.id))
        .join(LoteriaResultado, NumeroAcierto.resultado_id == LoteriaResultado.id)
        .filter(LoteriaResultado.fecha >= desde)
        .scalar()
    ) or 0

    result = GanadoresSemanaOut(total_ganadores=total, dias=7)

    try:
        _get_redis().setex(cache_key, CACHE_TTL_WEEK, json.dumps(result.model_dump()))
    except Exception:
        logger.warning("Redis no disponible — respuesta no cacheada")

    return result


@router.get("/stats", response_model=GanadoresStatsOut)
def get_ganadores_stats(db: Session = Depends(get_db)):
    """
    Ganadores con el software: hoy / mes actual / año actual.
    TTL Redis: hoy=60s, mes=300s, año=1800s.
    """
    hoy = datetime.now(COL_TZ).date()
    cache_key = f"public:loterias:stats:{hoy}"

    try:
        cached = _get_redis().get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        logger.warning("Redis no disponible — consultando DB directamente")

    def _count(desde: date, hasta: date) -> int:
        return (
            db.query(func.count(NumeroAcierto.id))
            .join(LoteriaResultado, NumeroAcierto.resultado_id == LoteriaResultado.id)
            .filter(LoteriaResultado.fecha >= desde, LoteriaResultado.fecha <= hasta)
            .scalar()
        ) or 0

    inicio_mes  = hoy.replace(day=1)
    inicio_anio = hoy.replace(month=1, day=1)

    result = GanadoresStatsOut(
        hoy=_count(hoy, hoy),
        mes=_count(inicio_mes, hoy),
        anio=_count(inicio_anio, hoy),
    )

    # TTL más corto entre los tres (hoy es el más volátil)
    try:
        _get_redis().setex(cache_key, CACHE_TTL_TODAY, json.dumps(result.model_dump()))
    except Exception:
        logger.warning("Redis no disponible — respuesta no cacheada")

    return result
