from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import extract, text
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_current_user
from app.database import get_db
from app.models.cliente import Cliente
from app.models.referido import Referido
from app.routers.auth import (
    OTP_TTL_MINUTES,
    _enviar_whatsapp_otp,
    _generar_otp,
    _otp_store,
)
from app.services.notification_queue import push as _push_notif

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
    departamento: Optional[str] = Field(None, max_length=100)
    ciudad: Optional[str] = Field(None, max_length=100)
    barrio: Optional[str] = Field(None, max_length=100)


class RegistroSendOtpRequest(BaseModel):
    celular: str = Field(..., min_length=7, max_length=15)
    codigo_pais: str = Field(default='57', max_length=10)


class RegistroEmbajadorRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    celular: str = Field(..., min_length=7, max_length=15)
    codigo_pais: str = Field(default='57', max_length=10)
    correo: Optional[str] = Field(None, max_length=200)
    cc: Optional[str] = Field(None, max_length=30)
    departamento: Optional[str] = Field(None, max_length=100)
    ciudad: Optional[str] = Field(None, max_length=100)
    barrio: Optional[str] = Field(None, max_length=100)
    otp_code: str = Field(..., min_length=6, max_length=6)


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
        "departamento": c.departamento,
        "ciudad": c.ciudad,
        "barrio": c.barrio,
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
    current_user.departamento = data.departamento or None
    current_user.ciudad = data.ciudad or None
    current_user.barrio = data.barrio or None

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


# ── Registro de Embajadores de Oro ────────────────────────────

_OTP_NS = "emb_"  # namespace para separar OTPs de registro del flujo de login


@router.post("/registro/send-otp", status_code=200)
def registro_send_otp(payload: RegistroSendOtpRequest, db: Session = Depends(get_db)):
    """Envía OTP de WhatsApp para iniciar el registro de un Embajador de Oro."""
    existing = db.query(Cliente).filter(Cliente.celular == payload.celular).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este número ya está registrado en el sistema.",
        )

    numero_completo = f"{payload.codigo_pais}{payload.celular}"
    codigo = _generar_otp()
    expira = datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)
    _otp_store[f"{_OTP_NS}{numero_completo}"] = (codigo, expira)
    _enviar_whatsapp_otp(numero_completo, codigo)
    return {"ok": True, "expira_en": OTP_TTL_MINUTES}


@router.post("/registro", status_code=201)
def registro_embajador(payload: RegistroEmbajadorRequest, db: Session = Depends(get_db)):
    """Registra un nuevo Embajador de Oro (tipo_cliente=3) con OTP verificado."""
    numero_completo = f"{payload.codigo_pais}{payload.celular}"
    llave_otp = f"{_OTP_NS}{numero_completo}"

    # Validar OTP
    entry = _otp_store.get(llave_otp)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código de verificación no encontrado. Solicita uno nuevo.",
        )
    codigo_guardado, expira = entry
    if datetime.now(timezone.utc) > expira:
        _otp_store.pop(llave_otp, None)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El código de verificación expiró. Solicita uno nuevo.",
        )
    if payload.otp_code != codigo_guardado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código de verificación incorrecto.",
        )
    _otp_store.pop(llave_otp, None)

    # Verificar que el celular no esté registrado (doble check post-OTP)
    existing = db.query(Cliente).filter(Cliente.celular == payload.celular).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este número ya está registrado en el sistema.",
        )

    # Generar codigo_vip con secuencia PG
    numero_seq = db.execute(text("SELECT nextval('seq_embajador_codigo')")).scalar()
    codigo_vip = f"E{numero_seq:05d}"

    nuevo = Cliente(
        nombre=payload.nombre.strip(),
        celular=payload.celular,
        codigo_pais=payload.codigo_pais,
        correo=payload.correo or None,
        cc=payload.cc or None,
        departamento=payload.departamento or None,
        ciudad=payload.ciudad or None,
        barrio=payload.barrio or None,
        tipo_cliente=3,
        codigo_vip=codigo_vip,
        enabled=True,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)

    token = create_access_token(str(nuevo.id))

    # Notificar código asignado por WhatsApp (best-effort, no bloqueante)
    try:
        numero_wa = f"{nuevo.codigo_pais}{nuevo.celular}"
        _push_notif("codigo_cliente", numero_wa, {
            "tipo_cliente": "embajador de oro",
            "codigo_vip": codigo_vip,
        })
    except Exception:
        pass

    return {
        "access_token": token,
        "token_type": "bearer",
        "aliado": _aliado_dict(nuevo),
    }
