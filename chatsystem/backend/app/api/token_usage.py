"""
Token usage API

Super-admin routes:
  GET /token-usage/all          — all tenants, optional ?year=&month= filters
  GET /token-usage/{tenant_id}  — single tenant history

Tenant-admin route:
  GET /token-usage/my           — own tenant history
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_super_admin
from app.db.session import get_db
from app.db.tenant import TenantContext, require_admin, resolve_tenant
from app.services.token_usage import get_usage_all_tenants, get_usage_for_tenant

router = APIRouter(prefix="/token-usage", tags=["token-usage"])


# ── Tenant-admin: own tenant ──────────────────────────────────────────────────

@router.get("/my")
async def my_usage(
    months: int = Query(default=6, ge=1, le=24),
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> list[dict[str, Any]]:
    rows = await get_usage_for_tenant(tenant.id, db, months=months)
    return [
        {**r, "updated_at": r["updated_at"].isoformat()}
        for r in rows
    ]


# ── Super-admin: all tenants ──────────────────────────────────────────────────

@router.get("/all")
async def list_all_usage(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_super_admin),
) -> list[dict[str, Any]]:
    rows = await get_usage_all_tenants(db, year=year, month=month)
    # Serialize UUIDs / datetimes to strings
    return [
        {**r, "tenant_id": str(r["tenant_id"]), "updated_at": r["updated_at"].isoformat()}
        for r in rows
    ]


@router.get("/{tenant_id}")
async def tenant_usage(
    tenant_id: uuid.UUID,
    months: int = Query(default=6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_super_admin),
) -> list[dict[str, Any]]:
    rows = await get_usage_for_tenant(tenant_id, db, months=months)
    return [
        {**r, "updated_at": r["updated_at"].isoformat()}
        for r in rows
    ]
