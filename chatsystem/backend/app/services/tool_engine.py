"""
Tool Engine — loads AgentTool rows from DB and builds LangChain tools
dynamically at runtime.

Supported types:
  HTTP   — calls an external REST endpoint
  SQL    — runs a read-only query against any DSN
  STATIC — returns a fixed text

Template variables available in http_url, http_body_tpl, sql_query, sql_dsn:
  {phone}           — conversation phone number
  {conversation_id} — conversation UUID
  {tenant_slug}     — tenant slug
  {env:VAR_NAME}    — value from os.environ["VAR_NAME"]

Security:
  - SQL engine enforces read-only (SELECT only, no DML).
  - HTTP requests use a configurable timeout (default 10s).
  - {env:...} substitution only reads existing env vars.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Any

import aiohttp
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.agent_tool import AgentTool, ToolType

logger = logging.getLogger(__name__)

# ── Template substitution ─────────────────────────────────────────────────────

_ENV_RE = re.compile(r"\{env:([A-Z0-9_]+)\}")


def _render(template: str, ctx: dict[str, str]) -> str:
    """Replace {key} and {env:VAR} placeholders."""
    def _replace_env(m: re.Match) -> str:
        var = m.group(1)
        val = os.environ.get(var, "")
        if not val:
            logger.warning("env var %s not set for tool template", var)
        return val

    result = _ENV_RE.sub(_replace_env, template)
    for key, val in ctx.items():
        result = result.replace(f"{{{key}}}", str(val))
    return result


# ── Executor functions ────────────────────────────────────────────────────────

async def _exec_http(tool: AgentTool, ctx: dict[str, str], params: dict[str, str]) -> str:
    url = _render(tool.http_url or "", {**ctx, **params})
    method = (tool.http_method or "GET").upper()

    headers: dict[str, str] = {}
    if tool.http_headers:
        for k, v in tool.http_headers.items():
            headers[k] = _render(str(v), {**ctx, **params})

    body: Any = None
    if tool.http_body_tpl:
        rendered = _render(tool.http_body_tpl, {**ctx, **params})
        try:
            body = json.loads(rendered)
        except json.JSONDecodeError:
            body = rendered

    timeout = aiohttp.ClientTimeout(total=tool.http_timeout_seconds or 10)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            req = session.request(method, url, headers=headers, json=body if isinstance(body, dict) else None, data=body if isinstance(body, str) else None)
            async with req as resp:
                text_resp = await resp.text()
                try:
                    data = json.loads(text_resp)
                    return json.dumps(data, ensure_ascii=False)
                except json.JSONDecodeError:
                    return text_resp
    except Exception as exc:
        logger.error("HTTP tool %s failed: %s", tool.name, exc)
        return f"Error al consultar el servicio: {exc}"


async def _exec_sql(tool: AgentTool, ctx: dict[str, str], params: dict[str, str]) -> str:
    if not tool.sql_dsn or not tool.sql_query:
        return "Tool SQL mal configurada (falta dsn o query)."

    dsn = _render(tool.sql_dsn, {**ctx, **params})
    query = _render(tool.sql_query, {**ctx, **params})

    # Safety: only allow SELECT statements
    stripped = query.strip().upper()
    if not stripped.startswith("SELECT"):
        logger.error("SQL tool %s tried non-SELECT: %s", tool.name, query[:80])
        return "Solo se permiten consultas SELECT."

    try:
        engine = create_async_engine(dsn, pool_pre_ping=True)
        async with engine.connect() as conn:
            result = await conn.execute(text(query), params)
            rows = result.fetchall()
            cols = list(result.keys())
        await engine.dispose()

        if not rows:
            return "Sin resultados."
        lines = [", ".join(f"{c}: {v}" for c, v in zip(cols, row)) for row in rows]
        return "\n".join(lines)
    except Exception as exc:
        logger.error("SQL tool %s failed: %s", tool.name, exc)
        return f"Error en consulta: {exc}"


def _exec_static(tool: AgentTool) -> str:
    return tool.static_text or "(vacío)"


# ── Build LangChain StructuredTool from AgentTool row ─────────────────────────

def _build_tool(tool: AgentTool, ctx: dict[str, str]) -> StructuredTool:
    """
    Builds a LangChain StructuredTool from a DB row.
    `ctx` contains conversation-level variables: phone, conversation_id, tenant_slug.
    """
    param_names: list[str] = []

    if tool.tool_type == ToolType.SQL and tool.sql_params:
        param_names = [p for p in tool.sql_params if p not in ctx]
    elif tool.tool_type == ToolType.HTTP:
        # Extract {param} placeholders from url + body (excluding ctx keys and env: vars)
        sources = (tool.http_url or "") + (tool.http_body_tpl or "")
        found = re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", sources)
        param_names = [p for p in found if p not in ctx and not p.startswith("env:")]

    # Build a pydantic model for the tool's parameters
    fields: dict[str, Any] = {}
    for pname in param_names:
        fields[pname] = (str, Field(description=f"Valor para {pname}"))

    InputModel = create_model(f"{tool.name}_input", **fields) if fields else create_model(f"{tool.name}_input")

    async def _run(**kwargs: str) -> str:
        params = {k: str(v) for k, v in kwargs.items()}
        if tool.tool_type == ToolType.HTTP:
            return await _exec_http(tool, ctx, params)
        elif tool.tool_type == ToolType.SQL:
            return await _exec_sql(tool, ctx, params)
        else:
            return _exec_static(tool)

    return StructuredTool.from_function(
        coroutine=_run,
        name=tool.name,
        description=tool.description,
        args_schema=InputModel,
    )


# ── Public API ────────────────────────────────────────────────────────────────

async def load_tools(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    phone: str,
    conversation_id: str,
    tenant_slug: str,
) -> list[StructuredTool]:
    """
    Loads all enabled tools for the tenant and returns LangChain StructuredTools.
    """
    rows = await db.scalars(
        select(AgentTool).where(
            AgentTool.tenant_id == tenant_id,
            AgentTool.enabled == True,
        )
    )
    tools_rows = rows.all()
    if not tools_rows:
        return []

    ctx = {
        "phone": phone,
        "conversation_id": conversation_id,
        "tenant_slug": tenant_slug,
    }

    lc_tools: list[StructuredTool] = []
    for row in tools_rows:
        try:
            lc_tools.append(_build_tool(row, ctx))
        except Exception as exc:
            logger.error("Failed to build tool %s: %s", row.name, exc)

    logger.debug("Loaded %d tools for tenant %s", len(lc_tools), tenant_slug)
    return lc_tools
