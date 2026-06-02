import uuid
import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models.rifa import Rifa, RifaBoleta

router = APIRouter(prefix="/rifas", tags=["Rifas"])

COLOMBIA_TZ = ZoneInfo("America/Bogota")

_ACTIVA_CACHE: dict = {}   # keys: "ts", "value"
_ACTIVA_TTL = 120          # segundos


# ── Schemas ───────────────────────────────────────────────────────────────────────

class RifaPublicOut(BaseModel):
    id: str
    titulo: str
    descripcion: Optional[str]
    fecha_inicio: str
    fecha_fin: str
    seq_inicio: int
    seq_fin: int
    estado: str
    ganador_numero: Optional[int]
    tiene_imagen: bool
    total_boletas: int


class BoletaOut(BaseModel):
    numero: int
    asignado_en: datetime
    es_ganadora: bool


# ── Helpers ───────────────────────────────────────────────────────────────────────

def _to_public(rifa: Rifa, total: int) -> RifaPublicOut:
    return RifaPublicOut(
        id=str(rifa.id),
        titulo=rifa.titulo,
        descripcion=rifa.descripcion,
        fecha_inicio=str(rifa.fecha_inicio),
        fecha_fin=str(rifa.fecha_fin),
        seq_inicio=rifa.seq_inicio,
        seq_fin=rifa.seq_fin,
        estado=rifa.estado,
        ganador_numero=rifa.ganador_numero,
        tiene_imagen=rifa.imagen_data is not None,
        total_boletas=total,
    )


def _boletas_cliente(db: Session, rifa: Rifa, cliente_id) -> list[BoletaOut]:
    boletas = (
        db.query(RifaBoleta)
        .filter(RifaBoleta.rifa_id == rifa.id, RifaBoleta.cliente_id == cliente_id)
        .order_by(RifaBoleta.numero)
        .all()
    )
    return [
        BoletaOut(
            numero=b.numero,
            asignado_en=b.asignado_en,
            es_ganadora=(
                rifa.ganador_numero is not None
                and b.numero == rifa.ganador_numero
            ),
        )
        for b in boletas
    ]


# ── Endpoints ─────────────────────────────────────────────────────────────────────

@router.get("/imagen/{rifa_id}")
def get_imagen_publica(rifa_id: uuid.UUID, db: Session = Depends(get_db)):
    rifa = db.get(Rifa, rifa_id)
    if not rifa or not rifa.imagen_data:
        raise HTTPException(404, "Imagen no encontrada")
    return Response(
        content=rifa.imagen_data,
        media_type=rifa.imagen_mime,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/activa", response_model=Optional[RifaPublicOut])
def get_activa(db: Session = Depends(get_db)):
    now = time.time()
    if _ACTIVA_CACHE.get("ts") and now - _ACTIVA_CACHE["ts"] < _ACTIVA_TTL:
        return _ACTIVA_CACHE["value"]

    today = datetime.now(COLOMBIA_TZ).date()
    rifa = (
        db.query(Rifa)
        .filter(
            Rifa.estado == "activa",
            Rifa.fecha_inicio <= today,
            Rifa.fecha_fin >= today,
        )
        .first()
    )
    result = None
    if rifa:
        total = db.query(RifaBoleta).filter(RifaBoleta.rifa_id == rifa.id).count()
        result = _to_public(rifa, total)

    _ACTIVA_CACHE["ts"] = now
    _ACTIVA_CACHE["value"] = result
    return result


@router.get("/activa/mis-boletas", response_model=list[BoletaOut])
def mis_boletas_activa(
    db: Session = Depends(get_db),
    cliente=Depends(get_current_user),
):
    today = datetime.now(COLOMBIA_TZ).date()
    rifa = (
        db.query(Rifa)
        .filter(
            Rifa.estado == "activa",
            Rifa.fecha_inicio <= today,
            Rifa.fecha_fin >= today,
        )
        .first()
    )
    if not rifa:
        return []
    return _boletas_cliente(db, rifa, cliente.id)


@router.get("/historico", response_model=list[RifaPublicOut])
def get_historico(db: Session = Depends(get_db)):
    rifas = (
        db.query(Rifa)
        .filter(Rifa.estado == "finalizada")
        .order_by(Rifa.fecha_fin.desc())
        .all()
    )
    result = []
    for r in rifas:
        total = db.query(RifaBoleta).filter(RifaBoleta.rifa_id == r.id).count()
        result.append(_to_public(r, total))
    return result


@router.get("/historico/{rifa_id}/mis-boletas", response_model=list[BoletaOut])
def mis_boletas_historico(
    rifa_id: uuid.UUID,
    db: Session = Depends(get_db),
    cliente=Depends(get_current_user),
):
    rifa = db.get(Rifa, rifa_id)
    if not rifa:
        raise HTTPException(404, "Rifa no encontrada")
    return _boletas_cliente(db, rifa, cliente.id)
