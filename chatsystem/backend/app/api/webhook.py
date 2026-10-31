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
import json
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

# See ESPECIFICACION_REDIS_RIFA_ENUMERADA.md — a separate system (not this
# one) consumes this list via BLPOP to assign and send raffle tickets.
# chatsystem's only job here is to detect the button/typed reply and RPUSH;
# no dedup, no reply to the user, no other list or format.
RIFA_ENUMERADA_LIST = "rifa_enumerada:solicitudes"
RIFA_BOTON_TEXTO = "solicitar boletas"


def _extract_rifa_requests(payload: dict) -> list[dict]:
    """Find 'SOLICITAR BOLETAS' button taps (or typed equivalents) in a raw
    Meta webhook payload. Each dict has the RPUSH-ready {"celular",
    "contexto_wamid"} plus "wamid" (the triggering message's own id, used only
    to exclude it from the normal chat pipeline — never sent to Redis)."""
    requests: list[dict] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                msg_type = msg.get("type", "")
                if msg_type == "button":
                    text_value = msg.get("button", {}).get("text") or ""
                elif msg_type == "text":
                    text_value = msg.get("text", {}).get("body") or ""
                else:
                    continue

                if text_value.strip().lower() != RIFA_BOTON_TEXTO:
                    continue

                celular = msg.get("from") or ""
                if not celular:
                    continue

                request_data: dict = {"celular": celular, "wamid": msg.get("id", "")}
                contexto_wamid = msg.get("context", {}).get("id")
                if contexto_wamid:
                    request_data["contexto_wamid"] = contexto_wamid
                requests.append(request_data)
    return requests


# ── Helpers ───────────────────────────────────────────────────────────────────

def _verify_signature(body: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not signature.startswith("sha256="):
        logger.warning("Signature missing or bad format: %r", signature)
        return False
    expected = hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    match = hmac.compare_digest(f"sha256={expected}", signature)
    if not match:
        logger.warning(
            "Signature mismatch — received: %s | expected: sha256=%s",
            signature, expected,
        )
    return match


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
    import time as _time
    from app.db.tenant import _tenant_cache, _CACHE_TTL_S, TenantContext, set_tenant_schema
    from sqlalchemy import text as sa_text

    header = tenant_param.strip()
    _cached = _tenant_cache.get(header)
    if _cached and (_time.monotonic() - _cached[1]) < _CACHE_TTL_S:
        tenant = _cached[0]
    else:
        if _cached:
            del _tenant_cache[header]
        try:
            uuid.UUID(header)
            col = "id"
        except ValueError:
            col = "slug"
        async with AsyncSessionLocal() as db:
            row = await db.execute(
                sa_text(
                    f"SELECT id, slug, whatsapp_phone_id, whatsapp_token, "
                    f"webhook_secret, ai_system_prompt, "
                    f"whatsapp_template_name, whatsapp_template_language "
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
            whatsapp_template_name=row_data.whatsapp_template_name,
            whatsapp_template_language=row_data.whatsapp_template_language,
        )
        _tenant_cache[header] = (tenant, _time.monotonic())

    body = await request.body()

    # Signature validation — only enforce if Meta sends the header AND tenant has a secret configured
    sig = request.headers.get("X-Hub-Signature-256")
    logger.info(
        "Webhook POST tenant=%s | has_secret=%s | sig_header=%s",
        tenant.slug,
        bool(tenant.webhook_secret),
        sig or "(none)",
    )
    if tenant.webhook_secret and sig:
        if not _verify_signature(body, sig, tenant.webhook_secret):
            logger.error(
                "401 Bad signature for tenant=%s | body_len=%d",
                tenant.slug, len(body),
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    # Rifa enumerada: isolated side-channel, independent of the chat pipeline
    # below. A failure here must never break normal message ingestion.
    rifa_wamids: set[str] = set()
    try:
        rifa_requests = _extract_rifa_requests(payload)
        if rifa_requests:
            rifa_redis = await get_redis()
            for rifa_req in rifa_requests:
                rifa_wamids.add(rifa_req["wamid"])
                to_push = {"celular": rifa_req["celular"]}
                if "contexto_wamid" in rifa_req:
                    to_push["contexto_wamid"] = rifa_req["contexto_wamid"]
                await rifa_redis.rpush(RIFA_ENUMERADA_LIST, json.dumps(to_push, ensure_ascii=False))
                logger.info(
                    "Rifa enumerada: solicitud encolada celular=%s contexto=%s",
                    rifa_req["celular"], rifa_req.get("contexto_wamid"),
                )
    except Exception:
        logger.exception("Rifa enumerada: no se pudo encolar la solicitud")

    messages = parse_incoming_message(payload)
    if rifa_wamids:
        # The raffle-ticket request is handled entirely by the external rifa
        # system — the chatsystem bot must not see it or reply to it.
        messages = [m for m in messages if m.get("external_id") not in rifa_wamids]
    if not messages:
        # Status updates or other events — just ack
        return {"status": "ok"}

    redis = await get_redis()
    schema = f"t_{tenant.slug}"

    from app.db.session import make_tenant_session

    async with make_tenant_session(schema) as contact_db:
        await contact_db.execute(sa_text(f"SET search_path TO {schema}, public"))

        for msg_data in messages:
            phone = msg_data.get("phone_number") or msg_data.get("phone", "")
            bsuid = msg_data.get("bsuid", "")
            real_phone = msg_data.get("real_phone", "")
            # Meta sometimes discloses the real number alongside the BSUID in
            # the same event ("phone" then differs from "bsuid"); other times
            # it only arrives via the pedir_contacto "contacts" reply.
            disclosed_phone = real_phone or (phone if phone and phone != bsuid else "")

            linked_phone = ""
            if bsuid:
                linked_phone = await contact_db.scalar(
                    sa_text(f"SELECT id FROM {schema}.contactos WHERE bsuid = :bsuid LIMIT 1"),
                    {"bsuid": bsuid},
                ) or ""

            if bsuid and disclosed_phone and "." not in disclosed_phone and not linked_phone:
                # First time we see both identifiers together — remember the
                # link so every future message from this BSUID (even if Meta
                # later hides the phone again) keeps landing on the same
                # conversation instead of forking a new one.
                try:
                    await contact_db.execute(
                        sa_text(
                            f"INSERT INTO {schema}.contactos (id, bsuid, created_at) "
                            f"VALUES (:phone, :bsuid, NOW()) "
                            f"ON CONFLICT (id) DO UPDATE SET "
                            f"bsuid = COALESCE({schema}.contactos.bsuid, EXCLUDED.bsuid)"
                        ),
                        {"phone": disclosed_phone, "bsuid": bsuid},
                    )
                    await contact_db.commit()
                    linked_phone = disclosed_phone
                except Exception:
                    # Unique bsuid index conflict (already linked to another
                    # phone) or any other write issue — don't let a
                    # best-effort optimization break message ingestion.
                    await contact_db.rollback()
                    logger.warning("Could not link bsuid=%s to phone for tenant %s", bsuid, tenant.slug)

            # Stable identifier priority: a previously-linked real phone (keeps
            # continuity for users Meta later routes back through BSUID-only),
            # then the BSUID for privacy-protected users, then the raw phone.
            stable_id = linked_phone or bsuid or phone
            conversation_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{tenant.id}:{stable_id}",
            )
            await xadd(redis, MESSAGES_STREAM, {
                "tenant_id": str(tenant.id),
                "tenant_slug": tenant.slug,
                "conversation_id": str(conversation_id),
                "external_id": msg_data.get("external_id", ""),
                "phone": phone,
                "bsuid": bsuid,
                "username": msg_data.get("username", ""),
                "real_phone": msg_data.get("real_phone", ""),
                "content": msg_data.get("content", ""),
                "message_type": msg_data.get("message_type", "text"),
                "media_id": msg_data.get("media_id", ""),
                "received_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.info("Queued incoming msg from %s bsuid=%s (conv %s)", phone, bsuid or "-", conversation_id)

    return {"status": "ok"}
