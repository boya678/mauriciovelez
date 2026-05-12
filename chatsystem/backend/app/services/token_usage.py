"""
Token usage service.

Records and queries monthly token consumption per tenant
in the public.token_usage table.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def record_tokens(
    tenant_id: uuid.UUID,
    tokens_in: int,
    tokens_out: int,
    db: AsyncSession,
) -> None:
    """
    Atomically upsert (accumulate) token counts for the current UTC month.
    Uses INSERT … ON CONFLICT DO UPDATE so multiple concurrent workers are safe.
    """
    now = datetime.now(timezone.utc)
    await db.execute(
        text(
            """
            INSERT INTO public.token_usage
                (tenant_id, year, month, tokens_in, tokens_out, tokens_total, updated_at)
            VALUES
                (:tid, :yr, :mo, :tin, :tout, :ttot, now())
            ON CONFLICT (tenant_id, year, month) DO UPDATE SET
                tokens_in    = token_usage.tokens_in    + EXCLUDED.tokens_in,
                tokens_out   = token_usage.tokens_out   + EXCLUDED.tokens_out,
                tokens_total = token_usage.tokens_total + EXCLUDED.tokens_total,
                updated_at   = now()
            """
        ),
        {
            "tid": tenant_id,
            "yr": now.year,
            "mo": now.month,
            "tin": tokens_in,
            "tout": tokens_out,
            "ttot": tokens_in + tokens_out,
        },
    )
    await db.commit()


async def get_usage_for_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    months: int = 6,
) -> list[dict]:
    """
    Return monthly token usage for a single tenant, most recent first.
    """
    rows = await db.execute(
        text(
            """
            SELECT year, month, tokens_in, tokens_out, tokens_total, updated_at
            FROM public.token_usage
            WHERE tenant_id = :tid
            ORDER BY year DESC, month DESC
            LIMIT :lim
            """
        ),
        {"tid": tenant_id, "lim": months},
    )
    return [dict(r._mapping) for r in rows.fetchall()]


async def get_usage_all_tenants(
    db: AsyncSession,
    year: int | None = None,
    month: int | None = None,
) -> list[dict]:
    """
    Return token usage across all tenants, optionally filtered by year/month.
    Includes tenant name/slug via JOIN.
    """
    filters = ""
    params: dict = {}
    if year is not None:
        filters += " AND tu.year = :yr"
        params["yr"] = year
    if month is not None:
        filters += " AND tu.month = :mo"
        params["mo"] = month

    rows = await db.execute(
        text(
            f"""
            SELECT
                t.id       AS tenant_id,
                t.name     AS tenant_name,
                t.slug     AS tenant_slug,
                tu.year,
                tu.month,
                tu.tokens_in,
                tu.tokens_out,
                tu.tokens_total,
                tu.updated_at
            FROM public.token_usage tu
            JOIN public.tenants t ON t.id = tu.tenant_id
            WHERE 1=1 {filters}
            ORDER BY tu.year DESC, tu.month DESC, t.name ASC
            """
        ),
        params,
    )
    return [dict(r._mapping) for r in rows.fetchall()]
