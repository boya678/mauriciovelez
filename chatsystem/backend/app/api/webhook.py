"""
WhatsApp Cloud API webhook.

GET  /webhook  — Meta verification challenge
POST /webhook  — Incoming messages + status updates

Design constraints:
  • Must respond 200 OK in < 5 seconds to Meta
  • Does zero heavy work — just validates, deduplicates and writes to Redis Stream
  • Tenant resolved via header X-Tenant-ID or query param
"""
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, text

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.tenant import TenantContext, resolve_tenant
from app.models.conversation import Conversation
from app.models.tenant import Tenant
from app.redis.client import get_redis
from app.redis.streams import MESSAGES_STREAM, xadd
from app.services.whatsapp import parse_incoming_message

router = APIRouter(prefix="/webhook", tags=["webhook"])
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _verify_signature(body: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


# ── GET — Meta verification ───────────────────────────────────────────────────

@router.get("")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        return int(hub_challenge)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid verify token")


# ── POST — Incoming events ────────────────────────────────────────────────────

@router.post("")
async def receive_webhook(
    request: Request,
    tenant_param: str = Query(alias="tenant", default=""),
):
    # Resolve tenant from query param ?tenant= (Meta doesn't send custom headers)
    if not tenant_param:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing ?tenant= query parameter",
        )
    # Reuse resolve_tenant logic inline
    from app.db.tenant import _tenant_cache, TenantContext, set_tenant_schema
    from sqlalchemy import text as sa_text

    header = tenant_param.strip()
    if header in _tenant_cache:
        tenant = _tenant_cache[header]
    else:
        try:
            uuid.UUID(header)
            col = "id"
        except ValueError:
            col = "slug"
        async with AsyncSessionLocal() as db:
            row = await db.execute(
                sa_text(
                    f"SELECT id, slug, whatsapp_phone_id, whatsapp_token, "
                    f"webhook_secret, ai_system_prompt "
                    f"FROM public.tenants WHERE {col} = :val AND active = true"
                ),
                {"val": header},
            )
            row_data = row.fetchone()
        if not row_data:
            raise HTTPException(status_code=404, detail="Tenant not found or inactive")
        tenant = TenantContext(
            id=row_data.id,
            slug=row_data.slug,
            whatsapp_phone_id=row_data.whatsapp_phone_id or "",
            whatsapp_token=row_data.whatsapp_token or "",
            webhook_secret=row_data.webhook_secret,
            ai_system_prompt=row_data.ai_system_prompt,
        )
        _tenant_cache[header] = tenant

    body = await request.body()

    # Signature validation — only enforce if Meta sends the header AND tenant has a secret configured
    sig = request.headers.get("X-Hub-Signature-256")
    if tenant.webhook_secret and sig:
        if not _verify_signature(body, sig, tenant.webhook_secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    messages = parse_incoming_message(payload)
    if not messages:
        # Status updates or other events — just ack
        return {"status": "ok"}

    redis = await get_redis()
    schema = f"t_{tenant.slug}"

    for msg_data in messages:
        phone = msg_data.get("phone_number") or msg_data.get("phone", "")
        conversation_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{tenant.id}:{phone}",
        )
        await xadd(redis, MESSAGES_STREAM, {
            "tenant_id": str(tenant.id),
            "tenant_slug": tenant.slug,
            "conversation_id": str(conversation_id),
            "external_id": msg_data.get("external_id", ""),
            "phone": phone,
            "content": msg_data.get("content", ""),
            "message_type": msg_data.get("message_type", "text"),
            "received_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Queued incoming msg from %s (conv %s)", phone, conversation_id)

    return {"status": "ok"}
