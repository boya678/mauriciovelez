"""
Agents API

POST   /agents/login            — authenticate agent, return JWT
GET    /agents/me               — current agent profile
PUT    /agents/me/status        — set ONLINE | OFFLINE
GET    /agents                  — list agents (admin)
POST   /agents                  — create agent (admin)
PUT    /agents/{id}             — update agent (admin)
DELETE /agents/{id}             — deactivate agent (admin)
POST   /agents/heartbeat        — refresh presence TTL in Redis
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, verify_password, hash_password
from app.db.session import get_db
from app.db.tenant import TenantContext, get_tenant_db, resolve_tenant, require_agent, require_admin
from app.models.agent import Agent, AgentStatus
from app.redis.client import get_redis
from app.schemas.agent import AgentCreate, AgentOut, AgentUpdate, LoginRequest, TokenOut
from app.services.round_robin import (
    set_agent_online,
    set_agent_offline,
    refresh_presence,
)

router = APIRouter(prefix="/agents", tags=["agents"])
logger = logging.getLogger(__name__)


# ── Auth ──────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenOut)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_tenant_db),
    tenant: TenantContext = Depends(resolve_tenant),
):
    agent = await db.scalar(
        select(Agent).where(
            Agent.email == body.email,
            Agent.active == True,
        )
    )
    if not agent or not verify_password(body.password, agent.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token_data = {
        "sub": str(agent.id),
        "tenant_id": str(tenant.id),
        "tenant_slug": tenant.slug,
        "role": agent.role,
    }
    access_token = create_access_token(token_data)
    return TokenOut(access_token=access_token, token_type="bearer")


# ── Me ────────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=AgentOut)
async def get_me(
    db: AsyncSession = Depends(get_db),
    agent=Depends(require_agent),
):
    return AgentOut.model_validate(agent)


@router.put("/me/status")
async def set_status(
    agent_status: AgentStatus,
    db: AsyncSession = Depends(get_tenant_db),
    tenant: TenantContext = Depends(resolve_tenant),
    agent=Depends(require_agent),
):
    redis = await get_redis()
    if agent_status == AgentStatus.ONLINE:
        await set_agent_online(redis, str(tenant.id), str(agent.id))
    else:
        await set_agent_offline(redis, str(tenant.id), str(agent.id))

    agent.status = agent_status
    db.add(agent)
    await db.commit()
    return {"status": agent_status.value}


@router.post("/heartbeat")
async def heartbeat(
    tenant: TenantContext = Depends(resolve_tenant),
    agent=Depends(require_agent),
):
    redis = await get_redis()
    await refresh_presence(redis, str(tenant.id), str(agent.id))
    return {"ok": True}


# ── Admin CRUD ────────────────────────────────────────────────────────────────

@router.get("", response_model=list[AgentOut])
async def list_agents(
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    _=Depends(require_admin),
):
    result = await db.scalars(select(Agent).where(Agent.active == True))
    return [AgentOut.model_validate(a) for a in result.all()]


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    body: AgentCreate,
    db: AsyncSession = Depends(get_tenant_db),
    tenant: TenantContext = Depends(resolve_tenant),
    _=Depends(require_admin),
):
    existing = await db.scalar(select(Agent).where(Agent.email == body.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    agent = Agent(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        role=body.role,
        max_concurrent_chats=body.max_concurrent_chats,
        status=AgentStatus.OFFLINE,
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return AgentOut.model_validate(agent)


# ── Tenant settings (admin only) ──────────────────────────────────────────────

class PromptSettings(BaseModel):
    ai_system_prompt: str | None = None


@router.get("/settings", response_model=PromptSettings)
async def get_settings(
    tenant: TenantContext = Depends(resolve_tenant),
    _=Depends(require_admin),
):
    """Returns editable tenant settings (system prompt)."""
    return PromptSettings(ai_system_prompt=tenant.ai_system_prompt)


@router.put("/settings", response_model=PromptSettings)
async def update_settings(
    body: PromptSettings,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Updates the AI system prompt for this tenant."""
    from app.models.tenant import Tenant
    from app.db.tenant import _tenant_cache
    t = await db.scalar(select(Tenant).where(Tenant.id == tenant.id))
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found")
    t.ai_system_prompt = body.ai_system_prompt
    await db.commit()
    # Invalidate in-process cache so next request picks up new prompt
    _tenant_cache.pop(tenant.slug, None)
    _tenant_cache.pop(str(tenant.id), None)
    return PromptSettings(ai_system_prompt=t.ai_system_prompt)


@router.put("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentUpdate,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    _=Depends(require_admin),
):
    agent = await db.scalar(select(Agent).where(Agent.id == agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    for field, val in body.model_dump(exclude_none=True).items():
        if field == "password":
            agent.password_hash = hash_password(val)
        else:
            setattr(agent, field, val)

    await db.commit()
    await db.refresh(agent)
    return AgentOut.model_validate(agent)


@router.delete("/{agent_id}", status_code=204)
async def deactivate_agent(
    agent_id: uuid.UUID,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    _=Depends(require_admin),
):
    agent = await db.scalar(select(Agent).where(Agent.id == agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.active = False
    await db.commit()



