"""Registra en chatsystem (BD de chat, esquema del tenant) las notificaciones
WhatsApp enviadas directamente por la API de Meta desde esta plataforma
(no pasan por el webhook/API de chatsystem, así que nunca quedan en su
historial). Solo deja constancia — no crea conversaciones, no dispara IA,
no cambia colas ni notifica agentes.

Reglas:
- Si la conversación de ese celular NO existe en el schema del tenant, no se
  hace nada (no se crea conversación).
- Si existe, solo se actualizan updated_at/last_activity_at — nunca status
  ni assigned_agent_id.
- external_id (si se provee) evita duplicados vía UNIQUE constraint.
"""
import logging
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)

_tenant_id_cache: uuid.UUID | None = None


def _get_tenant_id(chat_db: Session) -> uuid.UUID | None:
    global _tenant_id_cache
    if _tenant_id_cache is not None:
        return _tenant_id_cache

    schema = settings.DATABASE_SCHEMA_2
    slug = schema[2:] if schema.startswith("t_") else schema
    row = chat_db.execute(
        text("SELECT id FROM public.tenants WHERE slug = :slug LIMIT 1"),
        {"slug": slug},
    ).first()
    if not row:
        logger.warning("No se encontró tenant con slug=%s en public.tenants", slug)
        return None
    _tenant_id_cache = row[0]
    return _tenant_id_cache


def registrar_notificacion_whatsapp(
    chat_db: Session,
    celular: str,
    content: str,
    external_id: str | None = None,
) -> None:
    """Registra una notificación saliente en la conversación existente del
    celular indicado. No falla el flujo llamador si algo sale mal."""
    try:
        schema = settings.DATABASE_SCHEMA_2
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', schema):
            logger.warning("Schema de chat inválido: %s", schema)
            return

        tenant_id = _get_tenant_id(chat_db)
        if tenant_id is None:
            return

        stable_id = re.sub(r"\D", "", celular)
        if not stable_id:
            return

        conversation_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{tenant_id}:{stable_id}")

        existe = chat_db.execute(
            text(f"SELECT 1 FROM {schema}.conversations WHERE id = :id"),
            {"id": str(conversation_id)},
        ).first()
        if not existe:
            return

        now = datetime.now(timezone.utc)
        chat_db.execute(
            text(
                f"UPDATE {schema}.conversations "
                f"SET updated_at = :now, last_activity_at = :now WHERE id = :id"
            ),
            {"now": now, "id": str(conversation_id)},
        )
        chat_db.execute(
            text(
                f"INSERT INTO {schema}.messages "
                f"(id, conversation_id, external_id, sender_type, content, message_type, status, created_at) "
                f"VALUES (:id, :conversation_id, :external_id, 'bot', :content, 'text', 'processed', :now) "
                f"ON CONFLICT (external_id) DO NOTHING"
            ),
            {
                "id": str(uuid.uuid4()),
                "conversation_id": str(conversation_id),
                "external_id": external_id,
                "content": content,
                "now": now,
            },
        )
        chat_db.commit()
    except Exception:
        chat_db.rollback()
        logger.exception("Error registrando notificación WhatsApp en chatsystem")
