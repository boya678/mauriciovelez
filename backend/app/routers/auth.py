from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.database import get_db
from app.models.cliente import Cliente
from app.schemas.cliente import LoginRequest, LoginResponse

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
