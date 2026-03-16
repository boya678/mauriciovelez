from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_current_user
from app.database import get_db
from app.models.cliente import Cliente
from app.models.suscripcion import Suscripcion
from app.schemas.cliente import LoginRequest, LoginResponse, VipVerifyRequest, UpdateMisDatosRequest

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.celular == payload.celular).first()
    es_nuevo = False

    if cliente is None:
        es_nuevo = True
        cliente = Cliente(
            nombre=payload.nombre,
            celular=payload.celular,
            correo=payload.correo,
            cc=payload.cc,
        )
        db.add(cliente)
        db.commit()
        db.refresh(cliente)

    token = create_access_token(subject=str(cliente.id))

    return LoginResponse(
        access_token=token,
        cliente=cliente,
        es_nuevo=es_nuevo,
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
    db.commit()
    db.refresh(cliente)

    from app.core.security import create_access_token
    token = create_access_token(subject=str(cliente.id))
    return LoginResponse(access_token=token, cliente=cliente, es_nuevo=False)
