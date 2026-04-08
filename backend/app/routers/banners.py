import base64
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.banner import Banner

router = APIRouter(prefix="/banners", tags=["Banners"])


class BannerPublico(BaseModel):
    id: str
    tipo: str
    texto: Optional[str]
    imagen_src: Optional[str]   # data URI lista para <img src="...">
    audiencia: str


@router.get("/activo", response_model=Optional[BannerPublico])
def get_banner_activo(
    vip: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    Devuelve el primer banner vigente y activo que aplique al usuario.
    - Si vip=true  → devuelve banners con audiencia 'todos' o 'vip'
    - Si vip=false → devuelve banners con audiencia 'todos' únicamente
    """
    ahora = datetime.now(timezone.utc)

    q = db.query(Banner).filter(
        Banner.activo == True,
        Banner.inicio <= ahora,
        Banner.fin >= ahora,
    )

    if not vip:
        q = q.filter(Banner.audiencia == "todos")

    b = q.order_by(Banner.inicio.desc()).first()
    if not b:
        return None

    imagen_src: Optional[str] = None
    if b.tipo == "imagen" and b.imagen_data and b.imagen_mime:
        encoded = base64.b64encode(b.imagen_data).decode("ascii")
        imagen_src = f"data:{b.imagen_mime};base64,{encoded}"

    return BannerPublico(
        id=str(b.id),
        tipo=b.tipo,
        texto=b.texto,
        imagen_src=imagen_src,
        audiencia=b.audiencia,
    )
