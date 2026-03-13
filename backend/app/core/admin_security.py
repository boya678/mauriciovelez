from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import get_db

_bearer = HTTPBearer()


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_platform_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": user_id, "role": role, "exp": expire, "iss": "admin"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def get_current_platform_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: Session = Depends(get_db),
):
    from app.models.platform_user import PlatformUser  # avoid circular

    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("iss") != "admin":
            raise exc
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise exc
    except JWTError:
        raise exc

    user = db.get(PlatformUser, user_id)
    if user is None or not user.active:
        raise exc
    return user


def require_admin(user=Depends(get_current_platform_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol admin")
    return user


def require_edit(user=Depends(get_current_platform_user)):
    if user.role not in ("admin", "edit"):
        raise HTTPException(status_code=403, detail="Se requiere rol edit o admin")
    return user
