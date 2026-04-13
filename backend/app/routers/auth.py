import random
import string
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, get_current_user
from app.database import get_db
from app.models.cliente import Cliente
from app.models.suscripcion import Suscripcion
from app.schemas.cliente import (
    OtpRequest,
    LoginRequest,
    LoginResponse,
    VipVerifyRequest,
    UpdateMisDatosRequest,
)
from app.services.numbers import assign_number, notificar_nuevo_numero_free, VIGENCIA_FREE
from pydantic import BaseModel, Field

router = APIRouter(prefix="/auth", tags=["Auth"])


class ReferidoRequest(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=50)
# ── OTP store en memoria: {celular: (codigo, expira_en)} ──────
_otp_store: dict[str, tuple[str, datetime]] = {}
OTP_TTL_MINUTES = 5


def _generar_otp() -> str:
    return ''.join(random.choices(string.digits, k=6))


def _enviar_whatsapp_otp(celular: str, codigo: str) -> None:
    """Envía el OTP via WhatsApp Business API (template 'otp')."""
    # El número debe incluir código de país sin '+'
    numero = celular if celular.startswith('57') else f'57{celular}'
    url = f'https://graph.facebook.com/v25.0/{settings.WHATSAPP_PHONE_ID}/messages'
    headers = {
        'Authorization': f'Bearer {settings.WHATSAPP_TOKEN}',
        'Content-Type': 'application/json',
    }
    body = {
        'messaging_product': 'whatsapp',
        'to': numero,
        'type': 'template',
        'template': {
            'name': settings.WHATSAPP_TEMPLATE_OTP,
            'language': {'code': 'es_CO'},
            'components': [
                {
                    'type': 'body',
                    'parameters': [{'type': 'text', 'text': codigo}],
                },
                {
                    'type': 'button',
                    'sub_type': 'url',
                    'index': '0',
                    'parameters': [{'type': 'text', 'text': codigo}],
                },
            ],
        },
    }
    resp = httpx.post(url, json=body, headers=headers, timeout=10)
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail='No se pudo enviar el código de verificación. Intenta de nuevo.',
        )


@router.post('/send-otp', status_code=200)
def send_otp(payload: OtpRequest):
    """Genera y envía un OTP de 6 dígitos por WhatsApp."""
    codigo = _generar_otp()
    expira = datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)
    _otp_store[payload.celular] = (codigo, expira)
    _enviar_whatsapp_otp(payload.celular, codigo)
    return {'ok': True, 'expira_en': OTP_TTL_MINUTES}

@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    # ── Buscar cliente ─────────────────────────────────────────
    cliente = db.query(Cliente).filter(Cliente.celular == payload.celular).first()

    if cliente is None:
        # Cliente nuevo: requiere OTP verificado
        if not payload.otp_code:
            raise HTTPException(status_code=403, detail='otp_required')

        entry = _otp_store.get(payload.celular)
        if not entry:
            raise HTTPException(status_code=400, detail='Código de verificación no encontrado. Solicita uno nuevo.')
        codigo_guardado, expira = entry
        if datetime.now(timezone.utc) > expira:
            _otp_store.pop(payload.celular, None)
            raise HTTPException(status_code=400, detail='El código de verificación expiró. Solicita uno nuevo.')
        if payload.otp_code != codigo_guardado:
            raise HTTPException(status_code=400, detail='Código de verificación incorrecto.')
        _otp_store.pop(payload.celular, None)  # invalidar tras uso

        cliente = Cliente(
            nombre=payload.nombre,
            celular=payload.celular,
            correo=payload.correo,
            cc=payload.cc,
        )
        db.add(cliente)
        db.flush()  # obtener el ID antes del commit
        nueva_free = assign_number(db, cliente.id, "free", VIGENCIA_FREE)
        free_number = nueva_free.number
        free_valid_until = nueva_free.valid_until
        celular_cliente = cliente.celular  # capturar antes del commit
        db.commit()
        db.refresh(cliente)
        if celular_cliente:
            notificar_nuevo_numero_free(celular_cliente, free_number, free_valid_until)
        es_nuevo = True
    else:
        # Cliente existente: acceso directo sin OTP
        es_nuevo = False

    token = create_access_token(subject=str(cliente.id))

    return LoginResponse(
        access_token=token,
        cliente=cliente,
        es_nuevo=es_nuevo,
        disabled_msg=settings.CLIENTE_DISABLED_MSG if not cliente.enabled else None,
    )


@router.post("/verify-vip")
def verify_vip(payload: VipVerifyRequest, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.id == payload.cliente_id).first()
    if not cliente or not cliente.vip:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if not cliente.codigo_vip or cliente.codigo_vip != payload.codigo:
        raise HTTPException(status_code=400, detail="C\u00f3digo VIP incorrecto")
    return {"ok": True}


@router.get("/mi-suscripcion")
def mi_suscripcion(
    cliente: Cliente = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not cliente.vip:
        return {"vip": False, "fin": None}
    from datetime import timezone
    from datetime import datetime
    sus = (
        db.query(Suscripcion)
        .filter(
            Suscripcion.cliente_id == cliente.id,
            Suscripcion.activa == True,
            Suscripcion.fin >= datetime.now(timezone.utc),
        )
        .order_by(Suscripcion.fin.desc())
        .first()
    )
    return {"vip": True, "fin": sus.fin.isoformat() if sus else None}


@router.put("/mis-datos", response_model=LoginResponse)
def actualizar_mis_datos(
    payload: UpdateMisDatosRequest,
    cliente: Cliente = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not cliente.vip:
        raise HTTPException(status_code=403, detail="Solo clientes VIP pueden editar sus datos")

    # Verificar que el celular no pertenezca a otro cliente
    if payload.celular != cliente.celular:
        existing = db.query(Cliente).filter(
            Cliente.celular == payload.celular,
            Cliente.id != cliente.id,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="El número de celular ya está registrado")

    cliente.nombre = payload.nombre
    cliente.celular = payload.celular
    cliente.correo = payload.correo
    cliente.cc = payload.cc
    cliente.fecha_nacimiento = payload.fecha_nacimiento
    db.commit()
    db.refresh(cliente)

    from app.core.security import create_access_token
    token = create_access_token(subject=str(cliente.id))
    return LoginResponse(access_token=token, cliente=cliente, es_nuevo=False)


def _enviar_whatsapp_referido(celular: str, param1: str, param2: str) -> None:
    """Notifica al referente por WhatsApp cuando alguien usa su código."""
    numero = celular if celular.startswith('57') else f'57{celular}'
    url = f'https://graph.facebook.com/v25.0/{settings.WHATSAPP_PHONE_ID}/messages'
    headers = {
        'Authorization': f'Bearer {settings.WHATSAPP_TOKEN}',
        'Content-Type': 'application/json',
    }
    body = {
        'messaging_product': 'whatsapp',
        'to': numero,
        'type': 'template',
        'template': {
            'name': settings.WHATSAPP_TEMPLATE_NOTIFICACION_REFERIDO,
            'language': {'code': 'es_CO'},
            'components': [
                {
                    'type': 'body',
                    'parameters': [
                        {'type': 'text', 'text': param1},
                        {'type': 'text', 'text': param2},
                    ],
                },
            ],
        },
    }
    try:
        httpx.post(url, json=body, headers=headers, timeout=10)
    except Exception:
        pass  # notificación no bloqueante


@router.post('/referido', status_code=200)
def guardar_referido(
    payload: ReferidoRequest,
    current_user: Cliente = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Guarda el código de referido del cliente nuevo (solo una vez, silencioso si no existe)."""
    if current_user.referente:
        return {'ok': True}  # ya registrado, no sobrescribir

    referente = db.query(Cliente).filter(Cliente.codigo_vip == payload.codigo).first()
    if not referente:
        return {'ok': True}  # código no existe, falla silenciosa

    current_user.referente = payload.codigo
    db.commit()

    # TODO: confirmar con el usuario los dos parámetros del template WHATSAPP_TEMPLATE_NOTIFICACION_REFERIDO
    # Actualmente: param1 = nombre del nuevo usuario, param2 = celular del nuevo usuario
    _enviar_whatsapp_referido(referente.celular, current_user.nombre, current_user.celular)

    return {'ok': True}
