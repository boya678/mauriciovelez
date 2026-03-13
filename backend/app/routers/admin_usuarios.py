import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.admin_security import hash_password, require_admin
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.platform_user import PlatformUser

router = APIRouter(prefix="/admin/usuarios", tags=["Admin Usuarios"])


# ── Schemas ──────────────────────────────────────────────────────────────────────

class UsuarioOut(BaseModel):
    id: uuid.UUID
    cc: str
    nombre: str
    usuario: str
    role: str
    active: bool

    model_config = {"from_attributes": True}


class UsuarioCreate(BaseModel):
    cc: str
    nombre: str
    usuario: str
    clave: str
    role: str  # admin | edit | reader


class UsuarioUpdate(BaseModel):
    cc: Optional[str] = None
    nombre: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    clave: Optional[str] = None


# ── Helper audit ─────────────────────────────────────────────────────────────────

def _audit(db: Session, user, action: str, entity_id: str, detail: dict):
    db.add(AuditLog(
        platform_user_id=user.id,
        usuario=user.usuario,
        action=action,
        entity="platform_users",
        entity_id=entity_id,
        detail=detail,
    ))


# ── Endpoints ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[UsuarioOut])
def list_usuarios(
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    return db.query(PlatformUser).order_by(PlatformUser.nombre).all()


@router.post("", response_model=UsuarioOut, status_code=201)
def create_usuario(
    payload: UsuarioCreate,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    if payload.role not in ("admin", "edit", "reader"):
        raise HTTPException(status_code=400, detail="Role inválido. Use: admin, edit, reader")
    existing = db.query(PlatformUser).filter(PlatformUser.usuario == payload.usuario).first()
    if existing:
        raise HTTPException(status_code=409, detail="El usuario ya existe")
    nuevo = PlatformUser(
        cc=payload.cc,
        nombre=payload.nombre,
        usuario=payload.usuario,
        clave=hash_password(payload.clave),
        role=payload.role,
    )
    db.add(nuevo)
    _audit(db, user, "CREATE", str(nuevo.id), {"usuario": payload.usuario, "role": payload.role})
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.put("/{usuario_id}", response_model=UsuarioOut)
def update_usuario(
    usuario_id: uuid.UUID,
    payload: UsuarioUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    obj = db.get(PlatformUser, usuario_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    changes = payload.model_dump(exclude_none=True)
    if "clave" in changes:
        changes["clave"] = hash_password(changes["clave"])
    if "role" in changes and changes["role"] not in ("admin", "edit", "reader"):
        raise HTTPException(status_code=400, detail="Role inválido")
    for key, val in changes.items():
        setattr(obj, key, val)
    audit_changes = {k: v for k, v in changes.items() if k != "clave"}
    _audit(db, user, "UPDATE", str(usuario_id), audit_changes)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{usuario_id}", status_code=204)
def delete_usuario(
    usuario_id: uuid.UUID,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    obj = db.get(PlatformUser, usuario_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if str(obj.id) == str(user.id):
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")
    _audit(db, user, "DELETE", str(usuario_id), {"usuario": obj.usuario})
    db.delete(obj)
    db.commit()
