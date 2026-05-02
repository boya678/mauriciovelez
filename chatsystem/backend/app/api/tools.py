"""
Agent Tools API — CRUD para tools parametrizables por tenant.

GET    /tools          — list tools (admin)
POST   /tools          — create tool (admin)
GET    /tools/{id}     — get one tool (admin)
PUT    /tools/{id}     — update tool (admin)
DELETE /tools/{id}     — delete tool (admin)
POST   /tools/{id}/test — test a tool with sample input (admin)
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.tenant import TenantContext, resolve_tenant, require_admin
from app.models.agent_tool import AgentTool, ToolType

router = APIRouter(prefix="/tools", tags=["tools"])
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────

class AgentToolBase(BaseModel):
    name: str
    description: str
    tool_type: ToolType
    enabled: bool = True
    # HTTP
    http_url: str | None = None
    http_method: str | None = "GET"
    http_headers: dict | None = None
    http_body_tpl: str | None = None
    http_timeout_seconds: int | None = 10
    # SQL
    sql_dsn: str | None = None
    sql_query: str | None = None
    sql_params: list[str] | None = None
    # STATIC
    static_text: str | None = None


class AgentToolCreate(AgentToolBase):
    pass


class AgentToolUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tool_type: ToolType | None = None
    enabled: bool | None = None
    http_url: str | None = None
    http_method: str | None = None
    http_headers: dict | None = None
    http_body_tpl: str | None = None
    http_timeout_seconds: int | None = None
    sql_dsn: str | None = None
    sql_query: str | None = None
    sql_params: list[str] | None = None
    static_text: str | None = None


class AgentToolOut(AgentToolBase):
    id: uuid.UUID
    tenant_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TestToolRequest(BaseModel):
    params: dict[str, str] = {}


class TestToolResponse(BaseModel):
    result: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[AgentToolOut])
async def list_tools(
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    rows = await db.scalars(
        select(AgentTool)
        .where(AgentTool.tenant_id == tenant.id)
        .order_by(AgentTool.created_at)
    )
    return [AgentToolOut.model_validate(r) for r in rows.all()]


@router.post("", response_model=AgentToolOut, status_code=201)
async def create_tool(
    body: AgentToolCreate,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    tool = AgentTool(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        **body.model_dump(),
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return AgentToolOut.model_validate(tool)


@router.get("/{tool_id}", response_model=AgentToolOut)
async def get_tool(
    tool_id: uuid.UUID,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    tool = await db.scalar(
        select(AgentTool).where(AgentTool.id == tool_id, AgentTool.tenant_id == tenant.id)
    )
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return AgentToolOut.model_validate(tool)


@router.put("/{tool_id}", response_model=AgentToolOut)
async def update_tool(
    tool_id: uuid.UUID,
    body: AgentToolUpdate,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    tool = await db.scalar(
        select(AgentTool).where(AgentTool.id == tool_id, AgentTool.tenant_id == tenant.id)
    )
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    for field, val in body.model_dump(exclude_none=True).items():
        setattr(tool, field, val)
    tool.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(tool)
    return AgentToolOut.model_validate(tool)


@router.delete("/{tool_id}", status_code=204)
async def delete_tool(
    tool_id: uuid.UUID,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    tool = await db.scalar(
        select(AgentTool).where(AgentTool.id == tool_id, AgentTool.tenant_id == tenant.id)
    )
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    await db.delete(tool)
    await db.commit()


@router.post("/{tool_id}/test", response_model=TestToolResponse)
async def test_tool(
    tool_id: uuid.UUID,
    body: TestToolRequest,
    tenant: TenantContext = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Execute a tool with sample params and return the raw result."""
    from app.services.tool_engine import _exec_http, _exec_sql, _exec_static
    from app.models.agent_tool import ToolType

    tool = await db.scalar(
        select(AgentTool).where(AgentTool.id == tool_id, AgentTool.tenant_id == tenant.id)
    )
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    ctx = {"phone": "test", "conversation_id": "test", "tenant_slug": tenant.slug}
    params = body.params

    try:
        if tool.tool_type == ToolType.HTTP:
            result = await _exec_http(tool, ctx, params)
        elif tool.tool_type == ToolType.SQL:
            result = await _exec_sql(tool, ctx, params)
        else:
            result = _exec_static(tool)
    except Exception as exc:
        result = f"Error: {exc}"

    return TestToolResponse(result=result)
