from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.admin_security import create_platform_token, verify_password
from app.database import get_db
from app.models.platform_user import PlatformUser

router = APIRouter(prefix="/admin/auth", tags=["Admin Auth"])


class AdminLoginRequest(BaseModel):
    usuario: str
    clave: str


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    nombre: str


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)):
    user = db.query(PlatformUser).filter(PlatformUser.usuario == payload.usuario).first()
    if user is None or not user.active or not verify_password(payload.clave, user.clave):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )
    token = create_platform_token(str(user.id), user.role)
    return AdminLoginResponse(
        access_token=token,
        role=user.role,
        nombre=user.nombre,
    )
