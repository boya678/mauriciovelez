import json
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_platform_user
from app.database import get_db
from app.models.cliente import Cliente
from app.models.rifa import Rifa, RifaBoleta
from app.models.tipo_cliente import TipoCliente
from app.services.rifas import asignar_boletas_retroactivo

router = APIRouter(prefix="/admin/rifas", tags=["Admin Rifas"])

IMAGEN_MAX_BYTES = 5 * 1024 * 1024
IMAGEN_MIMES = {"image/jpeg", "image/png", "image/webp"}


# ── Schemas ───────────────────────────────────────────────────────────────────────

class RifaOut(BaseModel):
    id: str
    titulo: str
    descripcion: Optional[str]
    fecha_inicio: date
    fecha_fin: date
    seq_inicio: int
    seq_fin: int
    boletas_por_renovacion: int
    solo_vip: bool
    tipos_cliente: list
    ganador_numero: Optional[int]
    estado: str
    tiene_imagen: bool
    total_boletas: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TipoClienteOut(BaseModel):
    id: int
    nombre: str


class GanadorIn(BaseModel):
    numero: int


# ── Helper ────────────────────────────────────────────────────────────────────────

def _to_out(rifa: Rifa, total: int = 0) -> RifaOut:
    return RifaOut(
        id=str(rifa.id),
        titulo=rifa.titulo,
        descripcion=rifa.descripcion,
        fecha_inicio=rifa.fecha_inicio,
        fecha_fin=rifa.fecha_fin,
        seq_inicio=rifa.seq_inicio,
        seq_fin=rifa.seq_fin,
        boletas_por_renovacion=rifa.boletas_por_renovacion,
        solo_vip=rifa.solo_vip,
        tipos_cliente=rifa.tipos_cliente or [],
        ganador_numero=rifa.ganador_numero,
        estado=rifa.estado,
        tiene_imagen=rifa.imagen_data is not None,
        total_boletas=total,
        created_at=rifa.created_at,
    )


def _read_imagen(imagen: UploadFile) -> tuple[bytes, str]:
    if imagen.content_type not in IMAGEN_MIMES:
        raise HTTPException(400, "Formato de imagen no permitido (jpeg, png, webp)")
    data = imagen.file.read()
    if len(data) > IMAGEN_MAX_BYTES:
        raise HTTPException(400, "La imagen no puede superar 5 MB")
    return data, imagen.content_type


# ── Endpoints ─────────────────────────────────────────────────────────────────────

@router.get("/tipos-cliente", response_model=list[TipoClienteOut])
def listar_tipos_cliente(
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    rows = db.query(TipoCliente).order_by(TipoCliente.id).all()
    return [TipoClienteOut(id=r.id, nombre=r.nombre) for r in rows]


@router.get("", response_model=list[RifaOut])
def listar_rifas(
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    rifas = db.query(Rifa).order_by(Rifa.created_at.desc()).all()
    result = []
    for r in rifas:
        total = db.query(RifaBoleta).filter(RifaBoleta.rifa_id == r.id).count()
        result.append(_to_out(r, total))
    return result


@router.post("", response_model=RifaOut)
def crear_rifa(
    titulo: str = Form(...),
    descripcion: Optional[str] = Form(None),
    fecha_inicio: date = Form(...),
    fecha_fin: date = Form(...),
    seq_inicio: int = Form(0),
    seq_fin: int = Form(9999),
    boletas_por_renovacion: int = Form(1, ge=1),
    solo_vip: bool = Form(False),
    tipos_cliente: str = Form("[]"),
    imagen: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    if seq_inicio > seq_fin:
        raise HTTPException(400, "seq_inicio no puede ser mayor que seq_fin")
    if fecha_inicio > fecha_fin:
        raise HTTPException(400, "fecha_inicio no puede ser posterior a fecha_fin")

    tipos = json.loads(tipos_cliente) if tipos_cliente else []

    imagen_data, imagen_mime = None, None
    if imagen and imagen.filename:
        imagen_data, imagen_mime = _read_imagen(imagen)

    rifa = Rifa(
        titulo=titulo,
        descripcion=descripcion,
        imagen_data=imagen_data,
        imagen_mime=imagen_mime,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        seq_inicio=seq_inicio,
        seq_fin=seq_fin,
        boletas_por_renovacion=boletas_por_renovacion,
        solo_vip=solo_vip,
        tipos_cliente=tipos,
        estado="activa",
    )
    db.add(rifa)
    db.flush()  # para que rifa.id esté disponible antes de asignar boletas

    asignadas = asignar_boletas_retroactivo(db, rifa)
    db.commit()
    db.refresh(rifa)

    total = db.query(RifaBoleta).filter(RifaBoleta.rifa_id == rifa.id).count()
    return _to_out(rifa, total)


@router.get("/{rifa_id}/imagen")
def get_imagen(
    rifa_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    rifa = db.get(Rifa, rifa_id)
    if not rifa or not rifa.imagen_data:
        raise HTTPException(404, "Imagen no encontrada")
    return Response(content=rifa.imagen_data, media_type=rifa.imagen_mime)


@router.put("/{rifa_id}", response_model=RifaOut)
def editar_rifa(
    rifa_id: uuid.UUID,
    titulo: str = Form(...),
    descripcion: Optional[str] = Form(None),
    fecha_inicio: date = Form(...),
    fecha_fin: date = Form(...),
    seq_inicio: int = Form(0),
    seq_fin: int = Form(9999),
    boletas_por_renovacion: int = Form(1, ge=1),
    solo_vip: bool = Form(False),
    tipos_cliente: str = Form("[]"),
    imagen: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    rifa = db.get(Rifa, rifa_id)
    if not rifa:
        raise HTTPException(404, "Rifa no encontrada")
    if seq_inicio > seq_fin:
        raise HTTPException(400, "seq_inicio no puede ser mayor que seq_fin")

    rifa.titulo = titulo
    rifa.descripcion = descripcion
    rifa.fecha_inicio = fecha_inicio
    rifa.fecha_fin = fecha_fin
    rifa.seq_inicio = seq_inicio
    rifa.seq_fin = seq_fin
    rifa.boletas_por_renovacion = boletas_por_renovacion
    rifa.solo_vip = solo_vip
    rifa.tipos_cliente = json.loads(tipos_cliente) if tipos_cliente else []

    if imagen and imagen.filename:
        rifa.imagen_data, rifa.imagen_mime = _read_imagen(imagen)

    db.commit()
    db.refresh(rifa)
    total = db.query(RifaBoleta).filter(RifaBoleta.rifa_id == rifa.id).count()
    return _to_out(rifa, total)


@router.post("/{rifa_id}/ganador", response_model=RifaOut)
def registrar_ganador(
    rifa_id: uuid.UUID,
    body: GanadorIn,
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    rifa = db.get(Rifa, rifa_id)
    if not rifa:
        raise HTTPException(404, "Rifa no encontrada")
    if body.numero < rifa.seq_inicio or body.numero > rifa.seq_fin:
        raise HTTPException(
            400, f"El número debe estar entre {rifa.seq_inicio} y {rifa.seq_fin}"
        )
    rifa.ganador_numero = body.numero
    rifa.estado = "finalizada"
    db.commit()
    db.refresh(rifa)
    total = db.query(RifaBoleta).filter(RifaBoleta.rifa_id == rifa.id).count()
    return _to_out(rifa, total)


@router.post("/{rifa_id}/finalizar", response_model=RifaOut)
def finalizar_rifa(
    rifa_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    rifa = db.get(Rifa, rifa_id)
    if not rifa:
        raise HTTPException(404, "Rifa no encontrada")
    rifa.estado = "finalizada"
    db.commit()
    db.refresh(rifa)
    total = db.query(RifaBoleta).filter(RifaBoleta.rifa_id == rifa.id).count()
    return _to_out(rifa, total)


@router.get("/{rifa_id}/boletas")
def listar_boletas(
    rifa_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    if not db.get(Rifa, rifa_id):
        raise HTTPException(404, "Rifa no encontrada")

    q = (
        db.query(RifaBoleta, Cliente.nombre, Cliente.celular)
        .join(Cliente, RifaBoleta.cliente_id == Cliente.id)
        .filter(RifaBoleta.rifa_id == rifa_id)
    )
    total = q.count()
    rows = q.order_by(RifaBoleta.numero).offset((page - 1) * size).limit(size).all()

    items = [
        {
            "id": str(b.id),
            "numero": b.numero,
            "nombre": nombre,
            "celular": celular,
            "asignado_en": b.asignado_en,
        }
        for b, nombre, celular in rows
    ]
    return {"total": total, "page": page, "size": size, "items": items}
