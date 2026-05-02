"""
Tenant resolution and auth dependencies.

Tenant identified by:
  1. X-Tenant-ID header (UUID or slug)
  2. JWT claim `tenant_id` (fallback)

Sets search_path for every request via set_tenant_schema().

Exported dependencies:
  resolve_tenant  → TenantContext
  require_agent   → Agent model (JWT-authenticated)
  require_admin   → Agent model with role admin|superadmin
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, set_tenant_schema

logger = logging.getLogger(__name__)

# In-process cache: slug/id → TenantContext  (cleared on process restart)
_tenant_cache: dict[str, "TenantContext"] = {}

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class TenantContext:
    id: uuid.UUID
    slug: str
    whatsapp_phone_id: str
    whatsapp_token: str
    webhook_secret: str | None
    ai_system_prompt: str | None

    @property
    def schema(self) -> str:
        return f"t_{self.slug}"


async def resolve_tenant(request: Request) -> TenantContext:
    """
    FastAPI dependency. Resolves tenant from X-Tenant-ID header.
    Also sets the DB search_path context var so get_db() picks it up.
    """
    header = request.headers.get("X-Tenant-ID", "").strip()
    if not header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required",
        )

    if header in _tenant_cache:
        ctx = _tenant_cache[header]
        set_tenant_schema(ctx.schema)
        return ctx

    # Determine lookup column
    try:
        uuid.UUID(header)
        col = "id"
    except ValueError:
        col = "slug"

    async with AsyncSessionLocal() as db:
        row = await db.execute(
            text(
                f"SELECT id, slug, whatsapp_phone_id, whatsapp_token, "
                f"webhook_secret, ai_system_prompt "
                f"FROM public.tenants WHERE {col} = :val AND active = true"
            ),
            {"val": header},
        )
        tenant = row.fetchone()

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found or inactive")

    ctx = TenantContext(
        id=tenant.id,
        slug=tenant.slug,
        whatsapp_phone_id=tenant.whatsapp_phone_id or "",
        whatsapp_token=tenant.whatsapp_token or "",
        webhook_secret=tenant.webhook_secret,
        ai_system_prompt=tenant.ai_system_prompt,
    )
    _tenant_cache[header] = ctx
    set_tenant_schema(ctx.schema)
    return ctx


# ── Agent auth dependencies ───────────────────────────────────────────────────

async def require_agent(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    """Returns the DB Agent record from the JWT token.

    Superadmin JWTs (role=superadmin) bypass the DB lookup and return a
    virtual Agent with role='superadmin' so bootstrap operations work.
    """
    from app.core.security import decode_access_token
    from app.models.agent import Agent, AgentStatus
    from app.db.session import AsyncSessionLocal

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Superadmin JWT: bypass DB lookup — virtual agent object
    if payload.get("role") == "superadmin":
        virtual = Agent()
        virtual.id = uuid.UUID(int=0)
        virtual.tenant_id = uuid.UUID(int=0)
        virtual.name = "Superadmin"
        virtual.email = "superadmin"
        virtual.password_hash = ""
        virtual.role = "superadmin"
        virtual.status = AgentStatus.ONLINE
        virtual.active = True
        return virtual

    agent_id = payload.get("sub")
    tenant_slug = payload.get("tenant_slug", "")
    schema = f"t_{tenant_slug}"

    async with AsyncSessionLocal() as db:
        await db.execute(text(f"SET search_path TO {schema}, public"))
        agent = await db.scalar(
            select(Agent).where(Agent.id == uuid.UUID(agent_id), Agent.active == True)
        )

    if not agent:
        raise HTTPException(status_code=401, detail="Agent not found or inactive")

    return agent


async def require_admin(agent=Depends(require_agent)):
    """Restricts access to admin and superadmin roles."""
    if agent.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return agent


async def get_tenant_db(tenant: TenantContext = Depends(resolve_tenant)):
    """AsyncSession with search_path already set to the tenant schema.

    Use this instead of get_db for any endpoint that needs tenant-scoped tables.
    resolve_tenant runs FIRST (it's an explicit dependency here), so the schema
    is guaranteed to be correct when the session opens.

    The after_begin event re-sets the search_path on every new transaction so
    it survives connection release/re-acquire after commit (asyncpg pool behavior).
    """
    from sqlalchemy import event as sa_event

    schema = tenant.schema

    async with AsyncSessionLocal() as session:
        # Re-execute SET search_path at the start of every transaction on this
        # session (handles the case where asyncpg releases the connection to the
        # pool after commit and a fresh connection is checked out for refresh).
        @sa_event.listens_for(session.sync_session, "after_begin")
        def _set_search_path(sess, transaction, connection):
            connection.exec_driver_sql(f"SET search_path TO {schema}, public")

        await session.execute(text(f"SET search_path TO {schema}, public"))
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
