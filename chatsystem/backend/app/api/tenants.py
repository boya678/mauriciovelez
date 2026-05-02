"""
Tenants API (super-admin only)

POST   /tenants          — create tenant (provisions schema)
GET    /tenants          — list all tenants
GET    /tenants/{id}     — get tenant
PUT    /tenants/{id}     — update tenant config
DELETE /tenants/{id}     — soft-delete tenant
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import verify_super_admin
from app.db.session import get_db
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantOut, TenantUpdate

router = APIRouter(prefix="/tenants", tags=["tenants"])
logger = logging.getLogger(__name__)

TENANT_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.conversations (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    phone VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'new',
    assigned_agent_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS {schema}.messages (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES {schema}.conversations(id),
    external_id VARCHAR(128) UNIQUE,
    sender_type VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    message_type VARCHAR(30) NOT NULL DEFAULT 'text',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS {schema}.agents (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(30) NOT NULL DEFAULT 'agent',
    status VARCHAR(20) NOT NULL DEFAULT 'offline',
    max_concurrent_chats INTEGER NOT NULL DEFAULT 5,
    last_assigned_at TIMESTAMPTZ,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS {schema}.assignments (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES {schema}.conversations(id),
    agent_id UUID NOT NULL REFERENCES {schema}.agents(id),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    released_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_conv_status ON {schema}.conversations(status);
CREATE INDEX IF NOT EXISTS idx_conv_phone ON {schema}.conversations(phone);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON {schema}.messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_assign_agent ON {schema}.assignments(agent_id);
"""


async def _provision_tenant_schema(db: AsyncSession, slug: str) -> None:
    schema = f"t_{slug}"
    await db.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    for statement in TENANT_DDL.format(schema=schema).split(";"):
        stmt = statement.strip()
        if stmt:
            await db.execute(text(stmt))
    logger.info("Provisioned schema %s", schema)


@router.post("", response_model=TenantOut, status_code=201)
async def create_tenant(
    body: TenantCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_super_admin),
):
    existing = await db.scalar(select(Tenant).where(Tenant.slug == body.slug))
    if existing:
        raise HTTPException(status_code=409, detail="Slug already taken")

    tenant = Tenant(
        id=uuid.uuid4(),
        name=body.name,
        slug=body.slug,
        schema_name=f"t_{body.slug}",
        whatsapp_phone_id=body.whatsapp_phone_id,
        whatsapp_token=body.whatsapp_token,
        webhook_secret=body.webhook_secret,
        ai_system_prompt=body.ai_system_prompt,
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(tenant)
    await db.flush()

    await _provision_tenant_schema(db, body.slug)
    await db.commit()
    await db.refresh(tenant)
    return TenantOut.model_validate(tenant)


@router.get("", response_model=list[TenantOut])
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_super_admin),
):
    result = await db.scalars(select(Tenant).where(Tenant.active == True))
    return [TenantOut.model_validate(t) for t in result.all()]


@router.get("/{tenant_id}", response_model=TenantOut)
async def get_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_super_admin),
):
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantOut.model_validate(tenant)


@router.put("/{tenant_id}", response_model=TenantOut)
async def update_tenant(
    tenant_id: uuid.UUID,
    body: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_super_admin),
):
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    for field, val in body.model_dump(exclude_none=True).items():
        setattr(tenant, field, val)

    await db.commit()
    await db.refresh(tenant)
    return TenantOut.model_validate(tenant)


@router.delete("/{tenant_id}", status_code=204)
async def delete_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_super_admin),
):
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.active = False
    await db.commit()
