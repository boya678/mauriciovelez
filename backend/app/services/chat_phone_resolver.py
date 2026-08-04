import re
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


_PHONE_RE = re.compile(r"^\+?\d{10,15}$")
_SAFE_SCHEMA_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _is_phone_identifier(value: str | None) -> bool:
    if not value:
        return False
    return bool(_PHONE_RE.fullmatch(value.strip()))


def _validate_schema(schema: str) -> None:
    if not _SAFE_SCHEMA_RE.fullmatch(schema):
        raise ValueError(f"Nombre de schema invalido: {schema}")


def resolve_real_phone_from_identifier(chat_db: Session, schema: str, identifier: str | None) -> Optional[str]:
    """
    Resuelve un identificador de conversación a teléfono real.

    Casos:
    - Si `identifier` ya parece teléfono, lo retorna tal cual.
    - Si no, intenta buscar en `{schema}.contactos` por `bsuid`.
    - Fallback: busca por `id` en contactos.
    """
    if not identifier:
        return None

    _validate_schema(schema)

    ident = identifier.strip()
    if not ident:
        return None

    if _is_phone_identifier(ident):
        return ident

    row = chat_db.execute(text(f"""
        SELECT id
        FROM {schema}.contactos
        WHERE bsuid = :ident
        LIMIT 1
    """), {"ident": ident}).mappings().first()
    if row and row.get("id"):
        return str(row["id"])

    # Si llega solo el sufijo del BSUID (p.ej. 1949266959121697),
    # intenta contra la parte derecha de "CC.sufijo".
    row = chat_db.execute(text(f"""
        SELECT id
        FROM {schema}.contactos
        WHERE split_part(bsuid, '.', 2) = :ident
        LIMIT 1
    """), {"ident": ident}).mappings().first()
    if row and row.get("id"):
        return str(row["id"])

    row = chat_db.execute(text(f"""
        SELECT id
        FROM {schema}.contactos
        WHERE id = :ident
        LIMIT 1
    """), {"ident": ident}).mappings().first()
    if row and row.get("id"):
        return str(row["id"])

    return None


def resolve_real_phone_for_message(chat_db: Session, schema: str, msg_id: uuid.UUID) -> Optional[str]:
    """
    Obtiene `conversations.phone` del mensaje y resuelve teléfono real si aplica.
    """
    row = chat_db.execute(text(f"""
        SELECT c.phone
        FROM {schema}.messages m
        JOIN {schema}.conversations c ON c.id = m.conversation_id
        WHERE m.id = :msg_id
        LIMIT 1
    """), {"msg_id": msg_id}).mappings().first()
    if not row:
        return None

    raw_identifier = row.get("phone")
    return resolve_real_phone_from_identifier(chat_db, schema, raw_identifier) or raw_identifier
