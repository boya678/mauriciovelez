"""
Message stats service.

Accumulates monthly message counts per tenant in public.message_stats.
Counters never decrease — safe to keep even if conversation history is purged.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def record_messages(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    *,
    bot: int = 0,
    human: int = 0,
    user: int = 0,
) -> None:
    """
    Atomically increment message counters for the current UTC month.
    Skips the call if all counts are zero.
    """
    if not (bot or human or user):
        return

    now = datetime.now(timezone.utc)
    await db.execute(
        text(
            """
            INSERT INTO public.message_stats
                (tenant_id, year, month, bot_messages, human_messages, user_messages, updated_at)
            VALUES
                (:tid, :yr, :mo, :bot, :human, :user, now())
            ON CONFLICT (tenant_id, year, month) DO UPDATE SET
                bot_messages   = message_stats.bot_messages   + EXCLUDED.bot_messages,
                human_messages = message_stats.human_messages + EXCLUDED.human_messages,
                user_messages  = message_stats.user_messages  + EXCLUDED.user_messages,
                updated_at     = now()
            """
        ),
        {
            "tid": tenant_id,
            "yr": now.year,
            "mo": now.month,
            "bot": bot,
            "human": human,
            "user": user,
        },
    )
    await db.commit()


async def get_stats_for_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    months: int = 6,
) -> list[dict]:
    """
    Return monthly message stats for a single tenant, most recent first.
    """
    rows = await db.execute(
        text(
            """
            SELECT year, month, bot_messages, human_messages, user_messages, updated_at
              FROM public.message_stats
             WHERE tenant_id = :tid
             ORDER BY year DESC, month DESC
             LIMIT :lim
            """
        ),
        {"tid": tenant_id, "lim": months},
    )
    return [dict(r._mapping) for r in rows.fetchall()]


async def get_stats_all_tenants(
    db: AsyncSession,
    year: int | None = None,
    month: int | None = None,
) -> list[dict]:
    """
    Return message stats for all tenants (superadmin).
    """
    filters = "WHERE 1=1"
    params: dict = {}
    if year:
        filters += " AND ms.year = :yr"
        params["yr"] = year
    if month:
        filters += " AND ms.month = :mo"
        params["mo"] = month

    rows = await db.execute(
        text(
            f"""
            SELECT t.id AS tenant_id, t.name AS tenant_name, t.slug,
                   ms.year, ms.month,
                   ms.bot_messages, ms.human_messages, ms.user_messages,
                   ms.updated_at
              FROM public.message_stats ms
              JOIN public.tenants t ON t.id = ms.tenant_id
             {filters}
             ORDER BY ms.year DESC, ms.month DESC, t.name
            """
        ),
        params,
    )
    return [dict(r._mapping) for r in rows.fetchall()]
