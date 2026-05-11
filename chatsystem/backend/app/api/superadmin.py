"""
Superadmin API  (no tenant context required)

POST  /superadmin/login        — authenticate, get JWT (role=superadmin)
POST  /superadmin/bootstrap    — create FIRST superadmin (only works when table is empty)
GET   /superadmin/me           — current superadmin profile
GET   /superadmin/users        — list all superadmins
POST  /superadmin/users        — create another superadmin
DELETE /superadmin/users/{id}  — deactivate a superadmin
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.superadmin import Superadmin
from app.schemas.superadmin import (
    SuperadminCreate,
    SuperadminLoginRequest,
    SuperadminOut,
    SuperadminTokenOut,
)

router = APIRouter(prefix="/superadmin", tags=["superadmin"])
logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


# ── Auth dependency ───────────────────────────────────────────────────────────

async def _require_superadmin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Superadmin:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_access_token(credentials.credentials)
    if not payload or payload.get("role") != "superadmin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    sa_id = payload.get("sub")
    if not sa_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    sa = await db.scalar(
        select(Superadmin).where(Superadmin.id == uuid.UUID(sa_id), Superadmin.active == True)
    )
    if not sa:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Superadmin not found or inactive")
    return sa


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=SuperadminTokenOut)
async def login(
    body: SuperadminLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    sa = await db.scalar(
        select(Superadmin).where(Superadmin.email == body.email, Superadmin.active == True)
    )
    if not sa or not verify_password(body.password, sa.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token({"sub": str(sa.id), "role": "superadmin", "email": sa.email})
    return SuperadminTokenOut(access_token=token)


# ── Bootstrap (first superadmin — only when table is empty) ───────────────────

@router.post("/bootstrap", response_model=SuperadminOut, status_code=201)
async def bootstrap(
    body: SuperadminCreate,
    db: AsyncSession = Depends(get_db),
):
    count = await db.scalar(select(Superadmin).where(Superadmin.active == True))
    if count is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bootstrap is only available when no superadmins exist",
        )

    sa = Superadmin(
        id=uuid.uuid4(),
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(sa)
    await db.commit()
    await db.refresh(sa)
    logger.info("Bootstrap superadmin created: %s", sa.email)
    return SuperadminOut.model_validate(sa)


# ── Me ────────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=SuperadminOut)
async def get_me(sa: Superadmin = Depends(_require_superadmin)):
    return SuperadminOut.model_validate(sa)


# ── Users CRUD ────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[SuperadminOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: Superadmin = Depends(_require_superadmin),
):
    result = await db.scalars(select(Superadmin).where(Superadmin.active == True))
    return [SuperadminOut.model_validate(s) for s in result.all()]


@router.post("/users", response_model=SuperadminOut, status_code=201)
async def create_user(
    body: SuperadminCreate,
    db: AsyncSession = Depends(get_db),
    _: Superadmin = Depends(_require_superadmin),
):
    existing = await db.scalar(select(Superadmin).where(Superadmin.email == body.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    sa = Superadmin(
        id=uuid.uuid4(),
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(sa)
    await db.commit()
    await db.refresh(sa)
    return SuperadminOut.model_validate(sa)


@router.delete("/users/{sa_id}", status_code=204)
async def delete_user(
    sa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: Superadmin = Depends(_require_superadmin),
):
    if sa_id == current.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    sa = await db.scalar(select(Superadmin).where(Superadmin.id == sa_id))
    if not sa:
        raise HTTPException(status_code=404, detail="Superadmin not found")
    sa.active = False
    db.add(sa)
    await db.commit()
