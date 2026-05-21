from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import extract
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_current_user
from app.database import get_db
from app.models.cliente import Cliente
from app.models.referido import Referido

router = APIRouter(prefix="/aliados", tags=["Aliados"])


# ── Schemas ───────────────────────────────────────────────────

class AliadoLoginRequest(BaseModel):
    celular: str = Field(..., min_length=1, max_length=30)
    codigo_vip: str = Field(..., min_length=1, max_length=50)


class UpdatePerfilRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    correo: Optional[str] = Field(None, max_length=200)
    cc: Optional[str] = Field(None, max_length=30)
    fecha_nacimiento: Optional[str] = None  # YYYY-MM-DD


# ── Helpers ───────────────────────────────────────────────────

def _check_aliado(cliente: Cliente) -> None:
    if cliente.tipo_cliente not in (2, 3) or not cliente.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido a aliados tipo 2 o 3",
        )


def _aliado_dict(c: Cliente) -> dict:
    return {
        "id": str(c.id),
        "nombre": c.nombre,
        "celular": c.celular,
        "saldo": float(c.saldo),
        "codigo_vip": c.codigo_vip,
        "tipo_cliente": c.tipo_cliente,
        "fecha_nacimiento": c.fecha_nacimiento.isoformat() if c.fecha_nacimiento else None,
        "correo": c.correo,
        "cc": c.cc,
    }


# ── Endpoints ─────────────────────────────────────────────────

@router.post("/login", status_code=200)
def aliado_login(payload: AliadoLoginRequest, db: Session = Depends(get_db)):
    """Login para aliados tipo 2 y 3. Autentica con celular + codigo_vip propio."""
    cliente = (
        db.query(Cliente)
        .filter(
            Cliente.celular == payload.celular,
            Cliente.codigo_vip == payload.codigo_vip,
            Cliente.tipo_cliente.in_([2, 3]),
            Cliente.enabled.is_(True),
        )
        .first()
    )
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas o no tienes acceso de aliado",
        )
    token = create_access_token(str(cliente.id))
    return {
        "access_token": token,
        "token_type": "bearer",
        "aliado": _aliado_dict(cliente),
    }


@router.get("/perfil", status_code=200)
def get_perfil(current_user: Cliente = Depends(get_current_user)):
    """Retorna el perfil del aliado autenticado."""
    _check_aliado(current_user)
    return _aliado_dict(current_user)


@router.put("/perfil", status_code=200)
def update_perfil(
    data: UpdatePerfilRequest,
    current_user: Cliente = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Actualiza nombre, correo, cc y fecha de nacimiento del aliado."""
    _check_aliado(current_user)

    current_user.nombre = data.nombre
    current_user.correo = data.correo or None
    current_user.cc = data.cc or None

    if data.fecha_nacimiento:
        try:
            current_user.fecha_nacimiento = date.fromisoformat(data.fecha_nacimiento)
        except ValueError:
            pass
    else:
        current_user.fecha_nacimiento = None

    db.commit()
    db.refresh(current_user)
    return _aliado_dict(current_user)


@router.get("/mis-referidos", status_code=200)
def get_mis_referidos(
    mes: Optional[str] = None,
    current_user: Cliente = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista de clientes que se registraron usando el código de este aliado.
    Parámetro opcional: mes=YYYY-MM para filtrar por mes."""
    _check_aliado(current_user)

    query = (
        db.query(Referido, Cliente)
        .join(Cliente, Cliente.id == Referido.referido_id)
        .filter(Referido.referente_id == current_user.id)
    )

    if mes:
        try:
            anio, m = map(int, mes.split("-"))
            query = query.filter(
                extract("year", Referido.fecha_registro) == anio,
                extract("month", Referido.fecha_registro) == m,
            )
        except (ValueError, AttributeError):
            pass

    rows = query.order_by(Referido.fecha_registro.desc()).all()
    return [
        {
            "nombre": c.nombre,
            "celular": c.celular,
            "fecha_registro": r.fecha_registro.strftime("%Y-%m-%d") if r.fecha_registro else None,
        }
        for r, c in rows
    ]
