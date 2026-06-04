"""
Worker 2 — AI Worker

Consumes from  : ai_processing_stream
Publishes to   : outgoing_stream        (bot reply → WhatsApp)
                 human_assign_stream    (escalation → round-robin)

Responsibilities:
  1. Load full conversation history from DB
  2. Run LangGraph (classifier + specialist node)
  3. If bot reply → insert bot Message + publish to outgoing_stream
  4. If escalation → update conversation status to WAITING_HUMAN
                    + publish to human_assign_stream
  5. Publish WebSocket event to notify agents
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.agents.graph import run_graph
from app.db.session import AsyncSessionLocal, make_tenant_session
from app.db.tenant import set_tenant_schema
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageStatus, SenderType
from app.models.tenant import Tenant
from app.redis.client import get_redis
from app.redis.streams import (
    AI_STREAM,
    AI_CONSUMER_GROUP,
    HUMAN_ASSIGN_STREAM,
    OUTGOING_STREAM,
    ensure_consumer_group,
    xadd,
    xreadgroup,
    xack,
    xautoclaim,
)
from app.services.token_usage import record_tokens
from app.services.message_stats import record_messages
from app.services.tool_engine import load_tools
from app.websocket.manager import manager

logger = logging.getLogger(__name__)
import os
CONSUMER_NAME = f"ai-{os.environ.get('HOSTNAME', '1')}"
BATCH = 5
BLOCK_MS = 2000
# Generous: reasoning models (gpt-5-mini) can take 60-120s per turn. Avoid
# autoclaiming entries that are still being processed by the original consumer.
AUTOCLAIM_IDLE_MS = 240_000


async def _load_history(db, conversation_id: uuid.UUID) -> tuple[list[dict], int]:
    """Return (history, user_turns).

    history    : list of {role, content} dicts. Image messages are rendered as
                 [IMAGEN: <desc>] or [IMAGEN sin describir aún] so the LLM is
                 aware of attachments even though it can't see binary data.
    user_turns : count of USER messages in this conversation. Used to feed a
                 realistic turn counter into the graph (cache + escalation).
    """
    msgs = await db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    history: list[dict] = []
    user_turns = 0
    for m in msgs.all():
        is_user = m.sender_type == SenderType.USER
        role = "user" if is_user else "bot"
        if is_user:
            user_turns += 1
        content = m.content or ""
        mtype = getattr(m, "message_type", "text") or "text"
        if mtype == "image":
            desc = getattr(m, "imagen_descripcion", None)
            marker = f"[IMAGEN: {desc}]" if desc else "[IMAGEN sin describir aún]"
            content = f"{marker} {content}".strip()
        elif mtype == "audio" and not content:
            content = "[audio sin transcribir]"
        history.append({"role": role, "content": content})
    return history, user_turns


async def _process_entry(redis, entry_id: str, data: dict) -> None:
    tenant_id = data["tenant_id"]
    tenant_slug = data["tenant_slug"]
    conversation_id = uuid.UUID(data["conversation_id"])
    message_id = uuid.UUID(data["message_id"])
    phone = data["phone"]

    schema = f"t_{tenant_slug}"
    set_tenant_schema(schema)

    async with make_tenant_session(schema) as db:
        from sqlalchemy import text
        await db.execute(text(f"SET search_path TO {schema}, public"))

        # Idempotency: if this message was already processed (e.g. a previous
        # run completed but the ACK didn't reach Redis, so autoclaim re-delivered
        # it), skip it. Avoids duplicate LLM calls / duplicate bot replies.
        existing_status = await db.scalar(
            select(Message.status).where(Message.id == message_id)
        )
        if existing_status == MessageStatus.PROCESSED:
            logger.info(
                "Msg %s already PROCESSED \u2192 skipping (idempotent)", message_id,
            )
            return

        # Load tenant system prompt
        tenant = await db.scalar(
            select(Tenant).where(Tenant.id == uuid.UUID(tenant_id))
        )
        system_prompt = tenant.ai_system_prompt if tenant else ""

        # Load conversation + message count for turn tracking
        conv = await db.scalar(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        if conv is None:
            # Orphan message — just mark it processed so it doesn't show as PROCESSING forever
            await db.execute(
                update(Message)
                .where(Message.id == message_id)
                .values(status=MessageStatus.PROCESSED)
            )
            await db.commit()
            logger.warning("Conv %s not found, marking msg %s PROCESSED", conversation_id, message_id)
            return

        if conv.status not in (ConversationStatus.BOT_ACTIVE, ConversationStatus.NEW):
            # Conversation belongs to a human agent (or is awaiting one).
            # Don't run the bot, but DO forward the message to the human-assign
            # stream so the assigned agent (or assignment_worker) gets it.
            # Mark the message as PROCESSED so it doesn't stay in PROCESSING.
            await db.execute(
                update(Message)
                .where(Message.id == message_id)
                .values(status=MessageStatus.PROCESSED)
            )
            await db.commit()

            payload = {
                "tenant_id": tenant_id,
                "tenant_slug": tenant_slug,
                "conversation_id": str(conversation_id),
                "message_id": str(message_id),
                "phone": phone,
            }
            if conv.assigned_agent_id:
                payload["agent_id"] = str(conv.assigned_agent_id)
            await xadd(redis, HUMAN_ASSIGN_STREAM, payload)

            logger.info(
                "Conv %s status=%s \u2192 re-routed msg %s to human_assign_stream",
                conversation_id, conv.status, message_id,
            )
            return

        history, user_turns = await _load_history(db, conversation_id)

        # Check if there is an image awaiting description for this conversation.
        # We use a FIFO list so multiple images are handled in arrival order.
        pending_image_key = f"pending_images:{conversation_id}"
        pending_image_id_str = await redis.lindex(pending_image_key, 0)  # peek first
        has_pending_image = bool(pending_image_id_str)

        # Safety net: if the LLM has been asked about the same pending image
        # too many times without success, drop it automatically so the bot
        # eventually stops nagging. The worker only runs when the user sends
        # a new message, so a high cap is fine — it just protects against an
        # LLM that consistently ignores the [IMG_CTX:...] tag.
        MAX_IMAGE_ATTEMPTS = 6
        attempts_key: str | None = None
        if has_pending_image:
            pending_id_str = (
                pending_image_id_str.decode()
                if isinstance(pending_image_id_str, bytes)
                else pending_image_id_str
            )
            attempts_key = f"pending_image_attempts:{conversation_id}:{pending_id_str}"
            attempts = await redis.incr(attempts_key)
            await redis.expire(attempts_key, 3600)
            if attempts > MAX_IMAGE_ATTEMPTS:
                await redis.lpop(pending_image_key)
                await redis.delete(attempts_key)
                has_pending_image = False
                pending_image_id_str = None
                attempts_key = None
                logger.info(
                    "Dropped pending image for conv %s after %d attempts",
                    conversation_id, attempts - 1,
                )

        # Load dynamic tools for this tenant
        tools = await load_tools(
            db=db,
            tenant_id=uuid.UUID(tenant_id),
            phone=phone,
            conversation_id=str(conversation_id),
            tenant_slug=tenant_slug,
        )

        now = datetime.now(timezone.utc)

        # Run LangGraph with the real USER turn count so cache refresh and
        # auto-escalation by turns/confidence actually trigger.
        result = await run_graph(
            messages=history,
            tenant_system_prompt=system_prompt,
            tenant_id=tenant_id,
            conversation_id=str(conversation_id),
            turns=user_turns,
            tools=tools,
            phone=phone,
            has_pending_image=has_pending_image,
        )

        # Handle the IMG_CTX tag emitted by the specialist:
        #   - real description → persist on the image Message and clear the queue
        #   - "descartada" / "sin_descripcion" → just clear the queue (no description)
        #   - missing → keep image pending (counter above will drop it eventually)
        if has_pending_image:
            ctx = (result.get("imagen_contexto") or "").strip()
            ctx_low = ctx.lower()
            drop_only = ctx_low in ("descartada", "sin_descripcion", "sin descripcion")
            if ctx and not drop_only:
                pending_image_id = uuid.UUID(
                    pending_image_id_str.decode()
                    if isinstance(pending_image_id_str, bytes)
                    else pending_image_id_str
                )
                await db.execute(
                    update(Message)
                    .where(Message.id == pending_image_id)
                    .values(imagen_descripcion=ctx)
                )
                await db.commit()
                await redis.lpop(pending_image_key)
                if attempts_key:
                    await redis.delete(attempts_key)
                logger.info(
                    "Tagged image %s with descripcion=%r (conv %s)",
                    pending_image_id, ctx, conversation_id,
                )
            elif drop_only:
                await redis.lpop(pending_image_key)
                if attempts_key:
                    await redis.delete(attempts_key)
                logger.info(
                    "Dropped pending image for conv %s (LLM marked %s)",
                    conversation_id, ctx_low,
                )

        if result["needs_escalation"]:
            # Send a goodbye bot message first if there is a reply
            if result["bot_reply"]:
                farewell = Message(
                    id=uuid.uuid4(),
                    conversation_id=conversation_id,
                    sender_type=SenderType.BOT,
                    content=result["bot_reply"],
                    status=MessageStatus.PROCESSED,
                    created_at=now,
                )
                db.add(farewell)
                await xadd(redis, OUTGOING_STREAM, {
                    "tenant_id": tenant_id,
                    "tenant_slug": tenant_slug,
                    "phone": phone,
                    "message_id": str(farewell.id),
                    "content": result["bot_reply"],
                    "phone_id": tenant.whatsapp_phone_id if tenant else "",
                    "token": tenant.whatsapp_token if tenant else "",
                })

            # Mark the triggering user message as processed so it doesn't stay stuck.
            await db.execute(
                update(Message)
                .where(Message.id == message_id)
                .values(status=MessageStatus.PROCESSED)
            )

            # Update conversation status
            await db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(status=ConversationStatus.WAITING_HUMAN, updated_at=now)
            )
            await db.commit()

            await xadd(redis, HUMAN_ASSIGN_STREAM, {
                "tenant_id": tenant_id,
                "tenant_slug": tenant_slug,
                "conversation_id": str(conversation_id),
                "phone": phone,
            })

            # Record token usage for the classifier + farewell LLM calls
            t_in  = result.get("tokens_in",  0)
            t_out = result.get("tokens_out", 0)
            if t_in or t_out:
                try:
                    async with AsyncSessionLocal() as tok_db:
                        await record_tokens(uuid.UUID(tenant_id), t_in, t_out, tok_db)
                except Exception:
                    logger.warning("Failed to record tokens for tenant %s", tenant_id)

            # Notify agents via WebSocket
            await manager.publish(tenant_slug, {
                "type": "conversation_waiting",
                "conversation_id": str(conversation_id),
                "phone": phone,
            })
            logger.info("Escalated conv %s → WAITING_HUMAN", conversation_id)

        else:
            # Bot reply
            bot_msg = Message(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                sender_type=SenderType.BOT,
                content=result["bot_reply"],
                status=MessageStatus.PROCESSED,
                created_at=now,
            )
            db.add(bot_msg)
            await db.execute(
                update(Message)
                .where(Message.id == message_id)
                .values(status=MessageStatus.PROCESSED)
            )
            await db.commit()

            outgoing_payload: dict = {
                "tenant_id": tenant_id,
                "tenant_slug": tenant_slug,
                "phone": phone,
                "message_id": str(bot_msg.id),
                "content": result["bot_reply"],
                "phone_id": tenant.whatsapp_phone_id if tenant else "",
                "token": tenant.whatsapp_token if tenant else "",
            }
            interactive = result.get("interactive_payload")
            if interactive:
                import json as _json
                outgoing_payload["interactive_payload"] = _json.dumps(interactive)

            await xadd(redis, OUTGOING_STREAM, outgoing_payload)
            logger.info("Bot replied to conv %s", conversation_id)

            # Record token usage
            t_in  = result.get("tokens_in",  0)
            t_out = result.get("tokens_out", 0)
            if t_in or t_out:
                try:
                    async with AsyncSessionLocal() as tok_db:
                        await record_tokens(uuid.UUID(tenant_id), t_in, t_out, tok_db)
                except Exception:
                    logger.warning("Failed to record tokens for tenant %s", tenant_id)

            # Accumulate bot message counter
            try:
                async with AsyncSessionLocal() as stats_db:
                    await record_messages(uuid.UUID(tenant_id), stats_db, bot=1)
            except Exception:
                logger.warning("Failed to record bot message stat for tenant %s", tenant_id)


async def run(stop_event: asyncio.Event) -> None:
    redis = await get_redis()
    manager.set_redis(redis)
    await ensure_consumer_group(redis, AI_STREAM, AI_CONSUMER_GROUP)
    logger.info("ai_worker started")

    while not stop_event.is_set():
        try:
            stuck = await xautoclaim(
                redis, AI_STREAM, AI_CONSUMER_GROUP,
                CONSUMER_NAME, AUTOCLAIM_IDLE_MS, count=3,
            )
            for entry_id, data in stuck:
                try:
                    await _process_entry(redis, entry_id, data)
                    await xack(redis, AI_STREAM, AI_CONSUMER_GROUP, entry_id)
                except Exception:
                    logger.exception("Error reprocessing AI stuck entry %s", entry_id)

            entries = await xreadgroup(
                redis, AI_CONSUMER_GROUP, CONSUMER_NAME,
                AI_STREAM, count=BATCH, block=BLOCK_MS,
            )
            for entry_id, data in entries:
                try:
                    await _process_entry(redis, entry_id, data)
                    await xack(redis, AI_STREAM, AI_CONSUMER_GROUP, entry_id)
                except Exception:
                    logger.exception("Error in AI entry %s", entry_id)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("ai_worker loop error")
            await asyncio.sleep(2)

    await redis.aclose()
    logger.info("ai_worker stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    stop = asyncio.Event()
    asyncio.run(run(stop))
