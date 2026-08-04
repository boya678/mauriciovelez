import math
import re
import uuid
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_platform_user, require_admin
from app.core.config import settings
from app.database import get_chat_db, get_db
from app.models.cliente import Cliente
from app.models.comprobante_vip import ComprobanteVip
from app.models.mensajes_ia_procesado import MensajeIaProcesado
from app.models.audit_log import AuditLog
from app.models.tipo_cliente import TipoCliente
from app.models.transaccion_procesada import TransaccionProcesada
from app.services.chat_phone_resolver import resolve_real_phone_for_message, resolve_real_phone_from_identifier
from app.services.notification_queue import push as _push_notif
from app.services.suscripciones import renovar_cliente
from app.services.vision_ia import analizar_imagen_con_ia

router = APIRouter(prefix="/admin/transacciones", tags=["Admin Transacciones"])

COL_TZ = ZoneInfo("America/Bogota")


def _strip_country_code(phone: str) -> str:
    """Quita el código de país y devuelve los 10 dígitos locales colombianos."""
    digits = re.sub(r"\D", "", phone)
    # Formato típico WhatsApp Colombia: 573XXXXXXXXX (12 dígitos)
    if len(digits) == 12 and digits.startswith("57"):
        return digits[2:]
    # Si viene con prefijo 57 y tiene más/menos dígitos, tomar últimos 10
    if len(digits) > 10:
        return digits[-10:]
    return digits


def _is_valid_local_phone(phone: str | None) -> bool:
    return bool(phone and re.fullmatch(r"\d{10}", phone))


# ── Schemas de respuesta ──────────────────────────────────────────────────────

class ClienteInfo(BaseModel):
    registrado: bool
    nombre: Optional[str] = None
    vip: Optional[bool] = None
    activo: Optional[bool] = None
    tipo_nombre: Optional[str] = None
    tipo_cliente: Optional[int] = None


PAGE_SIZE = 50


class TransaccionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    phone: str
    phone_local: str
    media_content: Optional[str] = None
    media_mime_type: Optional[str] = None
    imagen_descripcion: Optional[str] = None
    cliente: ClienteInfo

    model_config = {"from_attributes": True}


class PagedTransacciones(BaseModel):
    total: int
    page: int
    pages: int
    items: list[TransaccionOut]


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("", response_model=PagedTransacciones)
def get_transacciones(
    fecha: Optional[date] = Query(default=None, description="Fecha YYYY-MM-DD (default: hoy en Colombia)"),
    page: int = Query(default=1, ge=1, description="Página (1-based)"),
    _user=Depends(get_current_platform_user),
    db: Session = Depends(get_db),
    chat_db: Session = Depends(get_chat_db),
):
    if fecha is None:
        fecha = datetime.now(COL_TZ).date()

    schema = settings.DATABASE_SCHEMA_2
    # Validar que el nombre de schema sea seguro (solo letras, dígitos, _)
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', schema):
        raise ValueError(f"Nombre de schema inválido: {schema}")

    # IDs ya procesados (ocultos) en portal DB
    procesados: set[uuid.UUID] = set(
        db.execute(
            select(TransaccionProcesada.id_externo).where(TransaccionProcesada.estado == False)  # noqa: E712
        ).scalars().all()
    )

    base_where = f"""
        FROM {schema}.messages m
        JOIN {schema}.conversations c ON c.id = m.conversation_id
        WHERE m.message_type = 'image'
          AND (m.created_at AT TIME ZONE 'America/Bogota')::date = :fecha
    """

    rows_all = chat_db.execute(text(f"""
        SELECT
            m.id,
            m.media_content,
            m.media_mime_type,
            m.imagen_descripcion,
            m.created_at,
            c.phone
        {base_where}
        ORDER BY m.created_at ASC
    """), {"fecha": fecha}).mappings().all()

    # Filtrar filas ya procesadas ANTES de contar/paginar para que total e items sean consistentes.
    rows_filtradas = [r for r in rows_all if r["id"] not in procesados]
    total = len(rows_filtradas)

    offset = (page - 1) * PAGE_SIZE
    rows = rows_filtradas[offset:offset + PAGE_SIZE]

    # Resolver posibles IDs/BSUIDs a telefono real usando contactos de BD2.
    resolved_cache: dict[str, str] = {}
    local_phones: list[str] = []
    for r in rows:
        phone_orig = r["phone"] or ""
        if not phone_orig:
            continue
        if phone_orig not in resolved_cache:
            resolved_cache[phone_orig] = resolve_real_phone_from_identifier(chat_db, schema, phone_orig) or phone_orig
        candidate = _strip_country_code(resolved_cache[phone_orig])
        if _is_valid_local_phone(candidate):
            local_phones.append(candidate)

    # Batch lookup de clientes por número local
    local_phones = list(set(local_phones))
    clientes_map: dict[str, Cliente] = {}
    tipos_map: dict[int, str] = {}
    if local_phones:
        found = db.execute(
            select(Cliente).where(Cliente.celular.in_(local_phones))
        ).scalars().all()
        for c in found:
            clientes_map[c.celular] = c
        tipo_ids = {c.tipo_cliente for c in found if c.tipo_cliente}
        if tipo_ids:
            tipos = db.execute(
                select(TipoCliente).where(TipoCliente.id.in_(tipo_ids))
            ).scalars().all()
            tipos_map = {t.id: t.nombre for t in tipos}

    items: list[TransaccionOut] = []
    for row in rows:
        phone_orig = row["phone"] or ""
        phone_resuelto = resolved_cache.get(phone_orig) or (resolve_real_phone_from_identifier(chat_db, schema, phone_orig) or phone_orig)
        phone_local = _strip_country_code(phone_resuelto)
        cli = clientes_map.get(phone_local)

        items.append(TransaccionOut(
            id=row["id"],
            created_at=row["created_at"],
            phone=phone_orig,
            phone_local=phone_local,
            media_content=row["media_content"],
            media_mime_type=row["media_mime_type"],
            imagen_descripcion=row["imagen_descripcion"],
            cliente=ClienteInfo(
                registrado=cli is not None,
                nombre=cli.nombre if cli else None,
                vip=cli.vip if cli else None,
                activo=cli.enabled if cli else None,
                tipo_nombre=tipos_map.get(cli.tipo_cliente) if cli else None,
                tipo_cliente=cli.tipo_cliente if cli else None,
            ),
        ))

    pages = max(1, math.ceil(total / PAGE_SIZE))
    return PagedTransacciones(total=total, page=page, pages=pages, items=items)


# ── Helpers internos ──────────────────────────────────────────────────────────

def _marcar_procesada(db: Session, id_externo: uuid.UUID) -> None:
    """Inserta o actualiza el registro de transaccion procesada con estado=False."""
    existente = db.execute(
        select(TransaccionProcesada).where(TransaccionProcesada.id_externo == id_externo)
    ).scalar_one_or_none()
    if existente is None:
        db.add(TransaccionProcesada(id_externo=id_externo, estado=False))
    else:
        existente.estado = False
    db.commit()


def _get_phone_from_chat(chat_db: Session, schema: str, msg_id: uuid.UUID) -> Optional[str]:
    return resolve_real_phone_for_message(chat_db, schema, msg_id)


# ── Acción: Eliminar (solo ocultar) ──────────────────────────────────────────

@router.post("/{id}/eliminar")
def eliminar_transaccion(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    _marcar_procesada(db, id)
    return {"ok": True}


# ── Acción: Chequear comprobante ──────────────────────────────────────────────

class ChequeoOut(BaseModel):
    analizado_por_ia: bool
    es_comprobante: Optional[bool]
    comprobante_num: Optional[str]
    monto_extraido: Optional[float]
    ya_procesado: bool
    procesado_para_celular: Optional[str]


@router.get("/{id}/chequear", response_model=ChequeoOut)
def chequear_comprobante(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    ia = db.execute(
        select(MensajeIaProcesado).where(MensajeIaProcesado.message_id == id)
    ).scalar_one_or_none()

    if not ia:
        return ChequeoOut(
            analizado_por_ia=False,
            es_comprobante=None,
            comprobante_num=None,
            monto_extraido=None,
            ya_procesado=False,
            procesado_para_celular=None,
        )

    duplicado = None
    if ia.comprobante_num:
        duplicado = db.execute(
            select(ComprobanteVip).where(ComprobanteVip.comprobante_num == ia.comprobante_num)
        ).scalar_one_or_none()

    # Si no encontró por comprobante_num, intenta por hash de imagen
    if duplicado is None and ia.image_hash:
        duplicado = db.execute(
            select(ComprobanteVip).where(ComprobanteVip.image_hash == ia.image_hash)
        ).scalars().first()

    return ChequeoOut(
        analizado_por_ia=True,
        es_comprobante=ia.es_comprobante,
        comprobante_num=ia.comprobante_num,
        monto_extraido=float(ia.monto_extraido) if ia.monto_extraido is not None else None,
        ya_procesado=duplicado is not None,
        procesado_para_celular=duplicado.celular if duplicado else None,
    )


# ── Acción: Registrar comprobante manualmente ─────────────────────────────────

class RegistrarComprobantePayload(BaseModel):
    comprobante_num_manual: Optional[str] = None  # override si la IA no extrajo uno
    descripcion: str = ""  # validado como obligatorio en el endpoint


@router.post("/{id}/registrar-comprobante")
def registrar_comprobante(
    id: uuid.UUID,
    payload: RegistrarComprobantePayload = Body(default=RegistrarComprobantePayload()),
    db: Session = Depends(get_db),
    chat_db: Session = Depends(get_chat_db),
    _user=Depends(require_admin),
):
    ia = db.execute(
        select(MensajeIaProcesado).where(MensajeIaProcesado.message_id == id)
    ).scalar_one_or_none()

    if not ia:
        raise HTTPException(status_code=400, detail="Esta imagen aún no fue analizada por la IA")

    if not ia.es_comprobante:
        raise HTTPException(status_code=400, detail="La IA no identificó esta imagen como un comprobante de pago")

    # Usar el número manual si viene; si no, el extraído por la IA
    comprobante_num = (payload.comprobante_num_manual or "").strip() or ia.comprobante_num
    if not comprobante_num:
        raise HTTPException(status_code=400, detail="Ingresa el número de comprobante manualmente")

    # Verificar duplicado por comprobante_num
    duplicado = db.execute(
        select(ComprobanteVip).where(ComprobanteVip.comprobante_num == comprobante_num)
    ).scalar_one_or_none()
    if not duplicado and ia.image_hash:
        duplicado = db.execute(
            select(ComprobanteVip).where(ComprobanteVip.image_hash == ia.image_hash)
        ).scalars().first()
    if duplicado:
        raise HTTPException(
            status_code=409,
            detail=f"El comprobante '{comprobante_num}' ya está registrado para el celular {duplicado.celular}",
        )

    schema = settings.DATABASE_SCHEMA_2
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', schema):
        raise ValueError(f"Nombre de schema inválido: {schema}")

    if not payload.descripcion.strip():
        raise HTTPException(status_code=400, detail="La descripción del pago es obligatoria")

    phone_orig = _get_phone_from_chat(chat_db, schema, id)
    celular = _strip_country_code(phone_orig) if phone_orig else ""
    if not _is_valid_local_phone(celular):
        celular = "desconocido"

    db.add(ComprobanteVip(
        comprobante_num=comprobante_num,
        celular=celular,
        monto=ia.monto_extraido or 0,
        descripcion=payload.descripcion.strip(),
        message_id=id,
        image_hash=ia.image_hash,
    ))
    db.add(AuditLog(
        platform_user_id=_user.id,
        usuario=_user.usuario,
        action="CREATE",
        entity="comprobantes_vip",
        entity_id=str(id),
        detail={"comprobante_num": comprobante_num, "celular": celular,
                "monto": float(ia.monto_extraido or 0), "descripcion": payload.descripcion.strip()},
    ))
    db.commit()
    return {"ok": True, "comprobante_num": comprobante_num, "celular": celular}


# ── Acción: Reprocesar con IA ────────────────────────────────────────────────

class ReprocesarOut(BaseModel):
    es_comprobante: bool
    comprobante_num: Optional[str]
    monto_extraido: Optional[float]
    accion: str   # renovado | cliente_creado | ya_procesado | monto_incorrecto | no_es_comprobante | sin_numero
    detalle: Optional[str] = None


@router.post("/{id}/reprocesar", response_model=ReprocesarOut)
def reprocesar_con_ia(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    chat_db: Session = Depends(get_chat_db),
    user=Depends(require_admin),
):
    if not settings.AZURE_OPENAI_ENDPOINT or not settings.AZURE_OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="Azure OpenAI no configurado")

    schema = settings.DATABASE_SCHEMA_2
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', schema):
        raise ValueError(f"Nombre de schema inválido: {schema}")

    # ── 1. Obtener imagen del chat DB ─────────────────────────────────────────
    row = chat_db.execute(text(f"""
        SELECT m.media_content, m.media_mime_type, c.phone
        FROM {schema}.messages m
        JOIN {schema}.conversations c ON c.id = m.conversation_id
        WHERE m.id = :msg_id AND m.media_content IS NOT NULL
        LIMIT 1
    """), {"msg_id": id}).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Imagen no encontrada en la BD de chat")

    base64_img: str = row["media_content"]
    mime_type: str = row["media_mime_type"] or "image/jpeg"
    phone_orig: str = row["phone"] or ""
    phone_resuelto = resolve_real_phone_from_identifier(chat_db, schema, phone_orig) or phone_orig
    phone_local = _strip_country_code(phone_resuelto)
    if not _is_valid_local_phone(phone_local):
        raise HTTPException(status_code=400, detail="No se pudo resolver un celular valido desde el identificador del chat")
    celular_wp = re.sub(r"\D", "", phone_resuelto) or f"57{phone_local}"

    # ── 2. Calcular hash ──────────────────────────────────────────────────────
    import base64 as _b64
    import hashlib
    from decimal import Decimal
    image_hash = hashlib.sha256(_b64.b64decode(base64_img)).hexdigest()

    # ── 3. Llamar a la IA ─────────────────────────────────────────────────────
    try:
        resultado_ia = analizar_imagen_con_ia(base64_img, mime_type)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error al llamar a la IA: {exc}")

    es_comprobante: bool = bool(resultado_ia.get("es_comprobante"))
    comprobante_num = resultado_ia.get("comprobante_num") or None
    monto_raw = resultado_ia.get("monto")
    monto = Decimal(str(monto_raw)) if monto_raw is not None else None

    # ── 4. Actualizar / reemplazar el registro de análisis IA ─────────────────
    ia_existente = db.execute(
        select(MensajeIaProcesado).where(MensajeIaProcesado.message_id == id)
    ).scalar_one_or_none()

    if ia_existente:
        ia_existente.es_comprobante = es_comprobante
        ia_existente.monto_extraido = monto
        ia_existente.comprobante_num = comprobante_num
        ia_existente.image_hash = image_hash
        from datetime import timezone
        ia_existente.processed_at = datetime.now(timezone.utc)
    else:
        db.add(MensajeIaProcesado(
            message_id=id,
            es_comprobante=es_comprobante,
            monto_extraido=monto,
            comprobante_num=comprobante_num,
            image_hash=image_hash,
        ))
    db.commit()

    monto_float = float(monto) if monto is not None else None

    if not es_comprobante:
        return ReprocesarOut(es_comprobante=False, comprobante_num=None,
                             monto_extraido=monto_float, accion="no_es_comprobante")

    if monto is None or int(monto) != settings.VIP_AMOUNT:
        return ReprocesarOut(es_comprobante=True, comprobante_num=comprobante_num,
                             monto_extraido=monto_float, accion="monto_incorrecto",
                             detalle=f"Monto extraído: {monto_float}, esperado: {settings.VIP_AMOUNT}")

    if not comprobante_num:
        return ReprocesarOut(es_comprobante=True, comprobante_num=None,
                             monto_extraido=monto_float, accion="sin_numero",
                             detalle="La IA no extrajo número de comprobante")

    # ── 5. Intentar registrar comprobante único ───────────────────────────────
    duplicado = db.execute(
        select(ComprobanteVip).where(ComprobanteVip.comprobante_num == comprobante_num)
    ).scalar_one_or_none()
    if not duplicado:
        duplicado = db.execute(
            select(ComprobanteVip).where(ComprobanteVip.image_hash == image_hash)
        ).scalars().first()

    if duplicado:
        _marcar_procesada(db, id)
        return ReprocesarOut(es_comprobante=True, comprobante_num=comprobante_num,
                             monto_extraido=monto_float, accion="ya_procesado",
                             detalle=f"Ya procesado para {duplicado.celular}")

    try:
        db.add(ComprobanteVip(
            comprobante_num=comprobante_num,
            celular=phone_local,
            monto=monto,
            descripcion="pago vip",
            message_id=id,
            image_hash=image_hash,
        ))
        db.add(AuditLog(
            platform_user_id=user.id,
            usuario=user.usuario,
            action="CREATE",
            entity="comprobantes_vip",
            entity_id=str(id),
            detail={"comprobante_num": comprobante_num, "celular": phone_local,
                    "monto": float(monto), "origen": "reprocesar"},
        ))
        db.flush()
    except Exception:
        db.rollback()
        _marcar_procesada(db, id)
        return ReprocesarOut(es_comprobante=True, comprobante_num=comprobante_num,
                             monto_extraido=monto_float, accion="ya_procesado",
                             detalle="Comprobante ya existente (detectado por hash)")

    # ── 6. Renovar o crear cliente ────────────────────────────────────────────
    cliente = db.execute(
        select(Cliente).where(Cliente.celular == phone_local)
    ).scalar_one_or_none()

    if cliente:
        if cliente.tipo_cliente != 1:
            db.rollback()
            raise HTTPException(status_code=400,
                                detail=f"Cliente {phone_local} es tipo {cliente.tipo_cliente}, no se puede renovar")
        nueva_sus, era_vip = renovar_cliente(
            db=db,
            cliente=cliente,
            platform_user_id=user.id,
            usuario=user.usuario,
            audit_action="RENOVAR_REPROCESAR",
            audit_entity="transacciones",
            audit_entity_id=str(id),
        )
        db.commit()
        _marcar_procesada(db, id)
        if not era_vip:
            from app.core.live_events import publish_event
            publish_event("nuevo_vip", {"nombre": cliente.nombre})
        return ReprocesarOut(es_comprobante=True, comprobante_num=comprobante_num,
                             monto_extraido=monto_float, accion="renovado",
                             detalle=f"{cliente.nombre} — suscripción hasta {nueva_sus.fin.date()}")
    else:
        # Cliente nuevo VIP
        from dateutil.relativedelta import relativedelta
        from datetime import timezone
        from app.models.cuenta_vip import acumular_cuenta_vip
        from app.services.numbers import (
            assign_number, notificar_codigo_asignado,
            notificar_nuevo_numero_free, notificar_nuevo_numero_vip,
        )
        _seq = db.execute(text("SELECT nextval('seq_vip_codigo')")).scalar()
        codigo_vip = f"{_seq:05d}"
        now = datetime.now(timezone.utc)
        from app.models.suscripcion import Suscripcion
        nuevo = Cliente(
            id=uuid.uuid4(),
            nombre=phone_local,
            celular=phone_local,
            codigo_pais="57",
            vip=True,
            enabled=True,
            tipo_cliente=1,
            codigo_vip=codigo_vip,
            saldo=0,
        )
        db.add(nuevo)
        db.flush()
        free = assign_number(db, nuevo.id, "free")
        db.add(Suscripcion(cliente_id=nuevo.id, inicio=now,
                           fin=now + relativedelta(months=1), activa=True))
        acumular_cuenta_vip(db)
        vip_num = assign_number(db, nuevo.id, "vip")
        db.flush()
        db.commit()
        _marcar_procesada(db, id)
        notificar_nuevo_numero_free(celular_wp, free.number, free.valid_until)
        notificar_nuevo_numero_vip(celular_wp, vip_num.number, vip_num.valid_until)
        notificar_codigo_asignado(celular_wp, 1, codigo_vip)
        from app.core.live_events import publish_event
        publish_event("nuevo_cliente", {"nombre": nuevo.nombre})
        return ReprocesarOut(es_comprobante=True, comprobante_num=comprobante_num,
                             monto_extraido=monto_float, accion="cliente_creado",
                             detalle=f"Nuevo cliente VIP creado: {phone_local}")


# ── Acción: Renovar suscripción ───────────────────────────────────────────────

@router.post("/{id}/renovar")
def renovar_desde_transaccion(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    chat_db: Session = Depends(get_chat_db),
    user=Depends(require_admin),
):
    schema = settings.DATABASE_SCHEMA_2
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', schema):
        raise ValueError(f"Nombre de schema inválido: {schema}")

    phone_orig = _get_phone_from_chat(chat_db, schema, id)
    if not phone_orig:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado en la BD de chat")

    phone_local = _strip_country_code(phone_orig)
    if not _is_valid_local_phone(phone_local):
        raise HTTPException(status_code=400, detail="No se pudo resolver un celular valido desde el identificador del chat")
    cliente = db.execute(
        select(Cliente).where(Cliente.celular == phone_local)
    ).scalar_one_or_none()
    if not cliente:
        raise HTTPException(status_code=404, detail=f"Cliente con celular {phone_local} no registrado")

    if cliente.tipo_cliente != 1:
        raise HTTPException(status_code=400, detail="Solo se puede renovar clientes de tipo 1")

    # ── Validar evidencia mínima del comprobante ──────────────────────────────
    # Para renovar desde transacciones exigimos que el análisis IA exista y
    # contenga tanto número de comprobante como hash de imagen.
    ia_registro = db.execute(
        select(MensajeIaProcesado).where(MensajeIaProcesado.message_id == id)
    ).scalar_one_or_none()

    if not ia_registro:
        raise HTTPException(
            status_code=400,
            detail="Debes chequear o reprocesar la imagen antes de renovar",
        )

    if not ia_registro.comprobante_num:
        raise HTTPException(
            status_code=400,
            detail="No se puede renovar: falta número de comprobante en el análisis IA",
        )

    if not ia_registro.image_hash:
        raise HTTPException(
            status_code=400,
            detail="No se puede renovar: falta hash de imagen en el análisis IA",
        )

    # ── Chequeo de comprobante duplicado ──────────────────────────────────────
    # Si ya existe por número o por hash, no debe renovar de nuevo.
    duplicado = db.execute(
        select(ComprobanteVip).where(
            ComprobanteVip.comprobante_num == ia_registro.comprobante_num
        )
    ).scalar_one_or_none()
    if duplicado is None:
        duplicado = db.execute(
            select(ComprobanteVip).where(
                ComprobanteVip.image_hash == ia_registro.image_hash
            )
        ).scalars().first()
    if duplicado:
        raise HTTPException(
            status_code=409,
            detail=f"El comprobante '{ia_registro.comprobante_num}' ya fue procesado anteriormente para el celular {duplicado.celular}",
        )

    # Comprobante nuevo — registrarlo antes de renovar
    db.add(ComprobanteVip(
        comprobante_num=ia_registro.comprobante_num,
        celular=phone_local,
        monto=ia_registro.monto_extraido or 0,
        descripcion="pago vip",
        message_id=id,
        image_hash=ia_registro.image_hash,
    ))
    db.flush()

    nueva, era_vip = renovar_cliente(
        db=db,
        cliente=cliente,
        platform_user_id=user.id,
        usuario=user.usuario,
        audit_action="RENOVAR_TRANSACCION",
        audit_entity="transacciones",
        audit_entity_id=str(id),
    )

    _marcar_procesada(db, id)

    if not era_vip:
        from app.core.live_events import publish_event
        publish_event("nuevo_vip", {"nombre": cliente.nombre})

    return {"ok": True, "cliente": cliente.nombre, "nueva_fin": nueva.fin.isoformat()}


# ── Acción: Enviar mensaje WhatsApp ──────────────────────────────────────────

class MensajePayload(BaseModel):
    texto: str


@router.post("/{id}/mensaje")
def enviar_mensaje_transaccion(
    id: uuid.UUID,
    payload: MensajePayload,
    db: Session = Depends(get_db),
    chat_db: Session = Depends(get_chat_db),
    _user=Depends(require_admin),
):
    if not settings.WHATSAPP_CONTACTO_TRANSACCIONES:
        raise HTTPException(status_code=503, detail="WHATSAPP_CONTACTO_TRANSACCIONES no configurado")

    schema = settings.DATABASE_SCHEMA_2
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', schema):
        raise ValueError(f"Nombre de schema inválido: {schema}")

    phone_orig = _get_phone_from_chat(chat_db, schema, id)
    if not phone_orig:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado en la BD de chat")

    numero_dest = re.sub(r"\D", "", phone_orig)
    if not numero_dest:
        raise HTTPException(status_code=400, detail="No se pudo resolver un numero de destino para WhatsApp")
    _push_notif("contacto_transacciones", numero_dest, {"texto": payload.texto})
    return {"ok": True}
