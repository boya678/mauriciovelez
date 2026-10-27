import io
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import openpyxl
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.admin_security import require_admin
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.cliente import Cliente
from app.models.tabla_numerologica import TablaNumerologicaEntrega, TablaNumerologicaFoto
from app.services.servicios_config import get_tabla_numerologica_config, set_tabla_numerologica_config
from app.services.tabla_numerologica import FOTO_ID

router = APIRouter(prefix="/admin/servicios/tabla-numerologica", tags=["Admin Servicios"])
public_router = APIRouter(prefix="/tabla-numerologica", tags=["Tabla numerologica"])

FOTO_MAX_BYTES = 5 * 1024 * 1024
COL_TZ = ZoneInfo("America/Bogota")


class TablaNumerologicaOut(BaseModel):
    activo: bool
    valor: int
    tiene_foto: bool


class TablaNumerologicaIn(BaseModel):
    activo: bool
    valor: int = Field(ge=0)


def _out(db: Session, activo: bool, valor: int) -> TablaNumerologicaOut:
    return TablaNumerologicaOut(
        activo=activo,
        valor=valor,
        tiene_foto=db.get(TablaNumerologicaFoto, FOTO_ID) is not None,
    )


@router.get("", response_model=TablaNumerologicaOut)
def get_tabla_numerologica(
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    cfg = get_tabla_numerologica_config(db)
    return _out(db, cfg.activo, cfg.valor)


@router.put("", response_model=TablaNumerologicaOut)
def put_tabla_numerologica(
    payload: TablaNumerologicaIn,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    if payload.activo and payload.valor <= 0:
        raise HTTPException(status_code=400, detail="Debes ingresar un monto mayor a 0 cuando el servicio esta activo")
    if payload.activo and db.get(TablaNumerologicaFoto, FOTO_ID) is None:
        raise HTTPException(status_code=400, detail="Debes subir la foto (JPG) antes de activar el servicio")

    cfg = set_tabla_numerologica_config(db, activo=payload.activo, valor=payload.valor)
    db.add(AuditLog(
        platform_user_id=user.id,
        usuario=user.usuario,
        action="UPDATE",
        entity="servicios.tabla_numerologica",
        entity_id="tabla_numerologica",
        detail={"activo": cfg.activo, "valor": cfg.valor},
    ))
    db.commit()
    return _out(db, cfg.activo, cfg.valor)


@router.post("/foto", response_model=TablaNumerologicaOut)
def subir_foto_tabla_numerologica(
    foto: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    data = foto.file.read()
    if foto.content_type != "image/jpeg" or not data.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=400, detail="La foto debe ser JPG")
    if len(data) > FOTO_MAX_BYTES:
        raise HTTPException(status_code=400, detail="La foto no puede superar 5 MB")

    existente = db.get(TablaNumerologicaFoto, FOTO_ID)
    if existente is None:
        db.add(TablaNumerologicaFoto(id=FOTO_ID, imagen_data=data, imagen_mime="image/jpeg"))
    else:
        existente.imagen_data = data
        existente.imagen_mime = "image/jpeg"
    db.add(AuditLog(
        platform_user_id=user.id,
        usuario=user.usuario,
        action="UPDATE",
        entity="servicios.tabla_numerologica",
        entity_id="tabla_numerologica",
        detail={"foto_bytes": len(data)},
    ))
    db.commit()

    cfg = get_tabla_numerologica_config(db)
    return _out(db, cfg.activo, cfg.valor)


@router.get("/exportar")
def exportar_entregas_tabla_numerologica(
    fecha_inicio: Optional[date] = Query(default=None),
    fecha_fin: Optional[date] = Query(default=None),
    _user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    if fecha_inicio is None and fecha_fin is None:
        fecha_fin = datetime.now(COL_TZ).date()
        fecha_inicio = fecha_fin - timedelta(days=30)

    fecha_col = func.date(func.timezone("America/Bogota", TablaNumerologicaEntrega.created_at))
    q = db.query(TablaNumerologicaEntrega, Cliente.nombre).outerjoin(
        Cliente, Cliente.celular == TablaNumerologicaEntrega.celular
    )
    if fecha_inicio:
        q = q.filter(fecha_col >= fecha_inicio)
    if fecha_fin:
        q = q.filter(fecha_col <= fecha_fin)
    filas = q.order_by(TablaNumerologicaEntrega.created_at.asc(), TablaNumerologicaEntrega.id.asc()).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tabla numerologica"
    ws.append(["Fecha", "Celular", "Nombre"])
    for entrega, nombre in filas:
        ws.append([
            entrega.created_at.astimezone(COL_TZ).strftime("%d/%m/%Y %H:%M"),
            entrega.celular,
            nombre or "",
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"tabla_numerologica_{fecha_inicio}_a_{fecha_fin}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@public_router.get("/foto")
def get_foto_publica(db: Session = Depends(get_db)):
    """Sin autenticación: Meta descarga la imagen desde esta URL al enviar la plantilla."""
    foto = db.get(TablaNumerologicaFoto, FOTO_ID)
    if foto is None:
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    return Response(
        content=foto.imagen_data,
        media_type=foto.imagen_mime,
        headers={"Cache-Control": "public, max-age=3600"},
    )
