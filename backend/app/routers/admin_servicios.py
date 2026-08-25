from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.admin_security import require_admin
from app.database import get_db
from app.models.audit_log import AuditLog
from app.services.servicios_config import (
    get_conferencia_config,
    get_conferencia_vip_config,
    get_numero_relampago_config,
    set_conferencia_config,
    set_conferencia_vip_config,
    set_numero_relampago_config,
)

router = APIRouter(prefix="/admin/servicios", tags=["Admin Servicios"])


class NumeroRelampagoOut(BaseModel):
    activo: bool
    valor: int
    numero: str


class NumeroRelampagoIn(BaseModel):
    activo: bool
    valor: int = Field(ge=0)
    numero: str = ""


class ConferenciaOut(BaseModel):
    activo: bool
    valor: int
    fecha_aviso: str
    link_youtube: str


class ConferenciaIn(BaseModel):
    activo: bool
    valor: int = Field(ge=0)
    fecha_aviso: str = ""
    link_youtube: str = ""


class ConferenciaVipOut(BaseModel):
    activo: bool
    valor: int
    fecha_aviso: str
    link_youtube: str


class ConferenciaVipIn(BaseModel):
    activo: bool
    valor: int = Field(ge=0)
    fecha_aviso: str = ""
    link_youtube: str = ""


@router.get("/numero-relampago", response_model=NumeroRelampagoOut)
def get_numero_relampago(
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    cfg = get_numero_relampago_config(db)
    return NumeroRelampagoOut(activo=cfg.activo, valor=cfg.valor, numero=cfg.numero)


@router.put("/numero-relampago", response_model=NumeroRelampagoOut)
def put_numero_relampago(
    payload: NumeroRelampagoIn,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    numero = (payload.numero or "").strip()
    if payload.activo and not numero:
        raise HTTPException(status_code=400, detail="Debes ingresar el numero relampago cuando el servicio esta activo")

    cfg = set_numero_relampago_config(
        db=db,
        activo=payload.activo,
        valor=payload.valor,
        numero=numero,
    )
    db.add(AuditLog(
        platform_user_id=user.id,
        usuario=user.usuario,
        action="UPDATE",
        entity="servicios.numero_relampago",
        entity_id="numero_relampago",
        detail={"activo": cfg.activo, "valor": cfg.valor, "numero": cfg.numero},
    ))
    db.commit()

    return NumeroRelampagoOut(activo=cfg.activo, valor=cfg.valor, numero=cfg.numero)


@router.get("/conferencia", response_model=ConferenciaOut)
def get_conferencia(
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    cfg = get_conferencia_config(db)
    return ConferenciaOut(
        activo=cfg.activo,
        valor=cfg.valor,
        fecha_aviso=cfg.fecha_aviso,
        link_youtube=cfg.link_youtube,
    )


@router.put("/conferencia", response_model=ConferenciaOut)
def put_conferencia(
    payload: ConferenciaIn,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    fecha_aviso = (payload.fecha_aviso or "").strip()
    link = (payload.link_youtube or "").strip()
    if payload.activo and not fecha_aviso:
        raise HTTPException(status_code=400, detail="Debes ingresar la fecha de aviso cuando conferencia esta activa")
    if payload.activo and not link:
        raise HTTPException(status_code=400, detail="Debes ingresar el link de YouTube cuando conferencia esta activa")

    cfg = set_conferencia_config(
        db=db,
        activo=payload.activo,
        valor=payload.valor,
        fecha_aviso=fecha_aviso,
        link_youtube=link,
    )
    db.add(AuditLog(
        platform_user_id=user.id,
        usuario=user.usuario,
        action="UPDATE",
        entity="servicios.conferencia",
        entity_id="conferencia",
        detail={
            "activo": cfg.activo,
            "valor": cfg.valor,
            "fecha_aviso": cfg.fecha_aviso,
            "link_youtube": cfg.link_youtube,
        },
    ))
    db.commit()

    return ConferenciaOut(
        activo=cfg.activo,
        valor=cfg.valor,
        fecha_aviso=cfg.fecha_aviso,
        link_youtube=cfg.link_youtube,
    )


@router.get("/conferencia-vip", response_model=ConferenciaVipOut)
def get_conferencia_vip(
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    cfg = get_conferencia_vip_config(db)
    return ConferenciaVipOut(
        activo=cfg.activo,
        valor=cfg.valor,
        fecha_aviso=cfg.fecha_aviso,
        link_youtube=cfg.link_youtube,
    )


@router.put("/conferencia-vip", response_model=ConferenciaVipOut)
def put_conferencia_vip(
    payload: ConferenciaVipIn,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    fecha_aviso = (payload.fecha_aviso or "").strip()
    link = (payload.link_youtube or "").strip()
    if payload.activo and not fecha_aviso:
        raise HTTPException(status_code=400, detail="Debes ingresar la fecha de aviso cuando conferencia VIP esta activa")
    if payload.activo and not link:
        raise HTTPException(status_code=400, detail="Debes ingresar el link de YouTube cuando conferencia VIP esta activa")

    cfg = set_conferencia_vip_config(
        db=db,
        activo=payload.activo,
        valor=payload.valor,
        fecha_aviso=fecha_aviso,
        link_youtube=link,
    )
    db.add(AuditLog(
        platform_user_id=user.id,
        usuario=user.usuario,
        action="UPDATE",
        entity="servicios.conferencia_vip",
        entity_id="conferencia_vip",
        detail={
            "activo": cfg.activo,
            "valor": cfg.valor,
            "fecha_aviso": cfg.fecha_aviso,
            "link_youtube": cfg.link_youtube,
        },
    ))
    db.commit()

    return ConferenciaVipOut(
        activo=cfg.activo,
        valor=cfg.valor,
        fecha_aviso=cfg.fecha_aviso,
        link_youtube=cfg.link_youtube,
    )
