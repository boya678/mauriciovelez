"""Servicio 'Tabla numerológica': envía solo una foto (plantilla sin variables) al pagar un monto."""
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.tabla_numerologica import TablaNumerologicaEntrega, TablaNumerologicaFoto
from app.services.notification_queue import push

FOTO_ID = 1


def registrar_entrega(db: Session, celular_local: str, message_id: uuid.UUID | None = None) -> None:
    """Deja constancia de la entrega. Hace flush pero NO commit."""
    db.add(TablaNumerologicaEntrega(celular=celular_local, message_id=message_id))
    db.flush()


def notificar_tabla_numerologica(db: Session, celular_wp: str) -> bool:
    """Encola el envío de la foto; False si aún no hay foto cargada."""
    foto = db.get(TablaNumerologicaFoto, FOTO_ID)
    if foto is None:
        return False
    version = int(foto.updated_at.timestamp())
    url = f"{settings.PUBLIC_API_URL.rstrip('/')}/tabla-numerologica/foto?v={version}"
    push("notificar_tabla_numerologica", celular_wp, {"url": url})
    return True
