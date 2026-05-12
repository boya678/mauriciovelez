"""
Message stats API

Super-admin routes:
  GET /message-stats/all          — all tenants, optional ?year=&month= filters
  GET /message-stats/{tenant_id}  — single tenant history

Tenant-admin route:
  GET /message-stats/my           — own tenant history
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_super_admin
from app.db.session import get_db
from app.db.tenant import TenantContext, require_admin, resolve_tenant
from app.services.message_stats import get_stats_all_tenants, get_stats_for_tenant

router = APIRouter(prefix="/message-stats", tags=["message-stats"])


# ── Tenant-admin: own tenant ──────────────────────────────────────────────────

@router.get("/my")
async def my_stats(
    months: int = Query(default=6, ge=1, le=24),
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> list[dict[str, Any]]:
    rows = await get_stats_for_tenant(tenant.id, db, months=months)
    return [
        {**r, "updated_at": r["updated_at"].isoformat()}
        for r in rows
    ]


# ── Super-admin: all tenants ──────────────────────────────────────────────────

@router.get("/all")
async def all_stats(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_super_admin),
) -> list[dict[str, Any]]:
    rows = await get_stats_all_tenants(db, year=year, month=month)
    return [
        {**r, "tenant_id": str(r["tenant_id"]), "updated_at": r["updated_at"].isoformat()}
        for r in rows
    ]


# ── Super-admin: single tenant ────────────────────────────────────────────────

@router.get("/{tenant_id}")
async def tenant_stats(
    tenant_id: uuid.UUID,
    months: int = Query(default=6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_super_admin),
) -> list[dict[str, Any]]:
    rows = await get_stats_for_tenant(tenant_id, db, months=months)
    return [
        {**r, "updated_at": r["updated_at"].isoformat()}
        for r in rows
    ]
