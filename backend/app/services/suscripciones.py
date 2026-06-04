"""
Lógica de negocio compartida para renovación de suscripciones.
Usada por admin_suscripciones y admin_transacciones.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.cliente import Cliente
from app.models.cuenta_vip import acumular_cuenta_vip
from app.models.numbers_users import NumberUser
from app.models.suscripcion import Suscripcion
from app.services.notification_queue import push as _push_notif
from app.services.numbers import assign_number, notificar_codigo_asignado, notificar_nuevo_numero_vip


def renovar_cliente(
    db: Session,
    cliente: Cliente,
    platform_user_id: uuid.UUID,
    usuario: str,
    audit_action: str = "RENOVAR",
    audit_entity: str = "suscripciones",
    audit_entity_id: Optional[str] = None,
) -> tuple[Suscripcion, bool]:
    """
    Ejecuta el flujo completo de renovación de suscripción para un cliente.

    - Inactiva suscripciones anteriores
    - Crea nueva suscripción (+1 mes)
    - Marca al cliente como VIP y habilitado
    - Asigna números free/vip si no tiene vigentes
    - Acumula cuenta VIP
    - Asigna boletas del evento activo
    - Registra audit log
    - NO hace commit (el caller debe hacerlo)

    Returns:
        (nueva_suscripcion, era_vip_antes)
    """
    now = datetime.now(timezone.utc)

    # 1. Inactivar todas las suscripciones del cliente
    db.query(Suscripcion).filter(
        Suscripcion.cliente_id == cliente.id,
    ).update({"activa": False}, synchronize_session="fetch")

    # 2. Calcular nueva fin desde la más reciente
    sus_actual = db.execute(
        select(Suscripcion)
        .where(Suscripcion.cliente_id == cliente.id)
        .order_by(Suscripcion.fin.desc())
        .limit(1)
    ).scalar_one_or_none()

    if sus_actual is not None:
        fin_actual = sus_actual.fin if sus_actual.fin.tzinfo else sus_actual.fin.replace(tzinfo=timezone.utc)
        base_fin = fin_actual if fin_actual > now else now
    else:
        base_fin = now

    nueva_fin = base_fin + relativedelta(months=1)

    nueva = Suscripcion(
        cliente_id=cliente.id,
        inicio=now,
        fin=nueva_fin,
        activa=True,
    )
    db.add(nueva)

    # 3. Asegurar que el cliente quede marcado como VIP y habilitado
    era_vip = cliente.vip
    if not cliente.vip:
        cliente.vip = True
    cliente.enabled = True

    # Si es cliente tipo 1 y no tiene código, asignar codigo_vip al renovar.
    if cliente.tipo_cliente == 1 and not cliente.codigo_vip:
        _seq = db.execute(text("SELECT nextval('seq_vip_codigo')")).scalar()
        cliente.codigo_vip = f"{_seq:05d}"
        if cliente.celular:
            celular_wp = f"{cliente.codigo_pais or '57'}{cliente.celular}"
            notificar_codigo_asignado(celular_wp, cliente.tipo_cliente, cliente.codigo_vip)

    # 4. Asignar números free/vip si no tiene vigentes
    today = datetime.now(ZoneInfo("America/Bogota")).date()

    free_row = db.execute(
        select(NumberUser).where(NumberUser.id_user == cliente.id, NumberUser.type == "free")
    ).scalar_one_or_none()
    if free_row is None or free_row.valid_until < today:
        assign_number(db, cliente.id, "free")

    vip_row = db.execute(
        select(NumberUser).where(NumberUser.id_user == cliente.id, NumberUser.type == "vip")
    ).scalar_one_or_none()
    if vip_row is None or vip_row.valid_until < today:
        nueva_vip = assign_number(db, cliente.id, "vip")
        if cliente.celular:
            celular_wp = f"{cliente.codigo_pais or '57'}{cliente.celular}"
            notificar_nuevo_numero_vip(celular_wp, nueva_vip.number, nueva_vip.valid_until)

    # 5. Acumular cuenta VIP
    acumular_cuenta_vip(db)

    # 6. Asignar boletas del evento activo
    from app.services.rifas import asignar_boletas_por_suscripcion
    asignar_boletas_por_suscripcion(db, cliente, nueva.id)

    # 7. Audit log
    db.add(AuditLog(
        platform_user_id=platform_user_id,
        usuario=usuario,
        action=audit_action,
        entity=audit_entity,
        entity_id=audit_entity_id or str(cliente.id),
        detail={
            "cliente_id": str(cliente.id),
            "nombre": cliente.nombre,
            "nueva_inicio": now.isoformat(),
            "nueva_fin": nueva_fin.isoformat(),
        },
    ))

    # Notificación WhatsApp de renovación con fecha de fin
    if settings.WHATSAPP_NOTIFICAR_RENOVACION and cliente.celular:
        celular_wp = f"{cliente.codigo_pais or '57'}{cliente.celular}"
        fecha_fin_str = nueva_fin.astimezone(ZoneInfo("America/Bogota")).strftime("%Y-%m-%d")
        _push_notif("notificar_renovacion", celular_wp, {"fecha_fin": fecha_fin_str})

    return nueva, era_vip
