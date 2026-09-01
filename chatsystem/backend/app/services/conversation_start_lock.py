"""PostgreSQL transaction lock for inbound/outbound conversation starts."""
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def conversation_start_lock_key(
    tenant_id: str | uuid.UUID,
    recipient: str,
) -> str:
    return f"start-conversation:{tenant_id}:{recipient}"


async def acquire_conversation_start_lock(
    db: AsyncSession,
    tenant_id: str | uuid.UUID,
    recipient: str,
) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": conversation_start_lock_key(tenant_id, recipient)},
    )
