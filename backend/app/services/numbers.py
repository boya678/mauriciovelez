"""
Servicio compartido de asignación de números.
Usado por: auth.py (primer número free), admin_clientes.py (primer número vip),
           scheduler.py (cron nocturno de reasignación).
"""
import logging
import random
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.numbers import Number
from app.models.numbers_historic import NumberHistoric
from app.models.numbers_users import NumberUser

VIGENCIA_FREE = 10  # días
VIGENCIA_VIP = 3    # días

logger = logging.getLogger(__name__)


def notificar_nuevo_numero_vip(celular: str, numero: str, valid_until: date) -> None:
    """Envía WhatsApp al cliente VIP cuando se le asigna un número nuevo."""
    metodo = numero[:-3] + numero[-3:][::-1] if len(numero) >= 3 else numero[::-1]
    param_numero = f"{numero} y con el metodo {metodo}"

    numero_dest = celular if celular.startswith('57') else f'57{celular}'
    url = f'https://graph.facebook.com/v25.0/{settings.WHATSAPP_PHONE_ID}/messages'
    headers = {
        'Authorization': f'Bearer {settings.WHATSAPP_TOKEN}',
        'Content-Type': 'application/json',
    }
    body = {
        'messaging_product': 'whatsapp',
        'to': numero_dest,
        'type': 'template',
        'template': {
            'name': settings.WHATSAPP_TEMPLATE_NOTIFICACION_NUMERO_VIP,
            'language': {'code': 'es_CO'},
            'components': [
                {
                    'type': 'body',
                    'parameters': [
                        {'type': 'text', 'text': param_numero},
                        {'type': 'text', 'text': valid_until.strftime('%d/%m/%Y')},
                    ],
                },
            ],
        },
    }
    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=10)
        if resp.status_code >= 400:
            logger.warning("WhatsApp nuevo_numero_vip falló (%s): %s", resp.status_code, resp.text)
    except Exception:
        logger.exception("Error al enviar WhatsApp nuevo_numero_vip a %s", celular)


def notificar_nuevo_numero_free(celular: str, numero: str, valid_until: date) -> None:
    """Envía WhatsApp al cliente cuando se le asigna un número free nuevo."""
    metodo = numero[:-3] + numero[-3:][::-1] if len(numero) >= 3 else numero[::-1]
    param_numero = f"{numero} y con el metodo {metodo}"

    numero_dest = celular if celular.startswith('57') else f'57{celular}'
    url = f'https://graph.facebook.com/v25.0/{settings.WHATSAPP_PHONE_ID}/messages'
    headers = {
        'Authorization': f'Bearer {settings.WHATSAPP_TOKEN}',
        'Content-Type': 'application/json',
    }
    body = {
        'messaging_product': 'whatsapp',
        'to': numero_dest,
        'type': 'template',
        'template': {
            'name': settings.WHATSAPP_TEMPLATE_NOTIFICACION_NUMERO_FREE,
            'language': {'code': 'es_CO'},
            'components': [
                {
                    'type': 'body',
                    'parameters': [
                        {'type': 'text', 'text': param_numero},
                        {'type': 'text', 'text': valid_until.strftime('%d/%m/%Y')},
                    ],
                },
            ],
        },
    }
    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=10)
        if resp.status_code >= 400:
            logger.warning("WhatsApp nuevo_numero_free falló (%s): %s", resp.status_code, resp.text)
    except Exception:
        logger.exception("Error al enviar WhatsApp nuevo_numero_free a %s", celular)
        logger.exception("Error al enviar WhatsApp nuevo_numero_free a %s", celular)


def assign_number(db: Session, id_user: uuid.UUID, num_type: str, validity_days: int) -> NumberUser:
    """
    Asigna un número del pool al usuario para el tipo dado.
    - Borra la asignación anterior del mismo tipo.
    - Si el pool está vacío, resetea todos a disponibles.
    - Prefija un dígito aleatorio 0-9 al número de 3 cifras del pool.
    - Registra en numbers_historic.
    - Hace flush pero NO commit (responsabilidad del llamador).
    """
    # Eliminar asignación anterior del mismo tipo
    db.execute(
        delete(NumberUser).where(
            NumberUser.id_user == id_user,
            NumberUser.type == num_type,
        )
    )
    db.flush()

    # Obtener números disponibles
    available = db.execute(
        select(Number).where(Number.assigned.is_(False))
    ).scalars().all()

    if not available:
        # Resetear pool completo
        db.execute(update(Number).values(assigned=False))
        db.flush()
        available = db.execute(
            select(Number).where(Number.assigned.is_(False))
        ).scalars().all()

    selected = random.choice(available)
    prefix = str(random.randint(0, 9))
    final_number = prefix + selected.number  # 4 dígitos: x + 3 cifras

    # Marcar el número del pool como ocupado
    selected.assigned = True

    today = datetime.now(ZoneInfo("America/Bogota")).date()

    assignment = NumberUser(
        number=final_number,
        id_user=id_user,
        date_assigned=today,
        valid_until=today + timedelta(days=validity_days),
        type=num_type,
    )
    db.add(assignment)

    # Histórico
    db.add(NumberHistoric(number=final_number, id_user=id_user, date=today, type=num_type))

    db.flush()
    return assignment
