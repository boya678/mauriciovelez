import base64
import io
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_platform_user
from app.database import get_db
from app.models.banner import Banner

router = APIRouter(prefix="/admin/banners", tags=["Admin Banners"])

# ── Constantes de validación de imagen ───────────────────────────────────────────
IMAGEN_ANCHO_MIN = 800
IMAGEN_RATIO_MIN = 2.0   # ancho/alto mínimo (horizontal)
IMAGEN_RATIO_MAX = 8.0   # ancho/alto máximo
IMAGEN_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
IMAGEN_MIMES_PERMITIDOS = {"image/jpeg", "image/png", "image/webp"}


# ── Schemas ───────────────────────────────────────────────────────────────────────

class BannerOut(BaseModel):
    id: str
    tipo: str
    texto: Optional[str]
    audiencia: str
    activo: bool
    inicio: datetime
    fin: datetime
    created_at: datetime
    tiene_imagen: bool

    class Config:
        from_attributes = True


class PaginatedBanners(BaseModel):
    total: int
    items: list[BannerOut]


# ── Helper ────────────────────────────────────────────────────────────────────────

def _to_out(b: Banner) -> BannerOut:
    return BannerOut(
        id=str(b.id),
        tipo=b.tipo,
        texto=b.texto,
        audiencia=b.audiencia,
        activo=b.activo,
        inicio=b.inicio,
        fin=b.fin,
        created_at=b.created_at,
        tiene_imagen=b.imagen_data is not None,
    )


def _validar_imagen(data: bytes, content_type: str) -> None:
    """Valida formato, dimensiones y tamaño de la imagen. Lanza HTTPException si falla."""
    try:
        from PIL import Image
    except ImportError:
        raise HTTPException(status_code=500, detail="Pillow no está instalado en el servidor.")

    if content_type not in IMAGEN_MIMES_PERMITIDOS:
        raise HTTPException(
            status_code=422,
            detail=f"Formato no permitido: '{content_type}'. Use JPEG, PNG o WebP.",
        )

    if len(data) > IMAGEN_MAX_BYTES:
        kb = len(data) // 1024
        raise HTTPException(
            status_code=422,
            detail=f"El archivo excede el límite de 2 MB (recibido: {kb} KB).",
        )

    try:
        img = Image.open(io.BytesIO(data))
        w, h = img.size
    except Exception:
        raise HTTPException(status_code=422, detail="No se pudo leer el archivo de imagen.")

    if w < IMAGEN_ANCHO_MIN:
        raise HTTPException(
            status_code=422,
            detail=f"El ancho mínimo es {IMAGEN_ANCHO_MIN} px. Recibida: {w} px.",
        )
    ratio = w / h
    if not (IMAGEN_RATIO_MIN <= ratio <= IMAGEN_RATIO_MAX):
        ratio_str = f"{ratio:.2f}"
        raise HTTPException(
            status_code=422,
            detail=(
                f"La imagen debe tener proporción horizontal entre {IMAGEN_RATIO_MIN}:1 y {IMAGEN_RATIO_MAX}:1. "
                f"Recibida: {w}×{h} px (ratio {ratio_str}:1). "
                f"Ejemplo válido: 1200×300, 1920×400, 800×200."
            ),
        )


# ── Endpoints admin ───────────────────────────────────────────────────────────────

@router.get("", response_model=PaginatedBanners)
def list_banners(
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    banners = db.query(Banner).order_by(Banner.created_at.desc()).all()
    return PaginatedBanners(total=len(banners), items=[_to_out(b) for b in banners])


@router.post("", response_model=BannerOut, status_code=201)
async def create_banner(
    tipo: str = Form(...),
    audiencia: str = Form(...),
    inicio: datetime = Form(...),
    fin: datetime = Form(...),
    texto: Optional[str] = Form(None),
    imagen: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    if tipo not in ("texto", "imagen"):
        raise HTTPException(status_code=422, detail="tipo debe ser 'texto' o 'imagen'.")
    if audiencia not in ("todos", "vip"):
        raise HTTPException(status_code=422, detail="audiencia debe ser 'todos' o 'vip'.")
    if fin <= inicio:
        raise HTTPException(status_code=422, detail="La fecha de fin debe ser posterior al inicio.")

    imagen_data: Optional[bytes] = None
    imagen_mime: Optional[str] = None

    if tipo == "texto":
        if not texto or not texto.strip():
            raise HTTPException(status_code=422, detail="El campo 'texto' es requerido para tipo 'texto'.")
    else:
        if not imagen:
            raise HTTPException(status_code=422, detail="Se debe adjuntar una imagen para tipo 'imagen'.")
        imagen_data = await imagen.read()
        imagen_mime = imagen.content_type or ""
        _validar_imagen(imagen_data, imagen_mime)

    b = Banner(
        id=uuid.uuid4(),
        tipo=tipo,
        texto=texto if tipo == "texto" else None,
        imagen_data=imagen_data,
        imagen_mime=imagen_mime,
        audiencia=audiencia,
        activo=True,
        inicio=inicio,
        fin=fin,
        created_at=datetime.now(timezone.utc),
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return _to_out(b)


@router.put("/{banner_id}", response_model=BannerOut)
async def update_banner(
    banner_id: str,
    tipo: str = Form(...),
    audiencia: str = Form(...),
    inicio: datetime = Form(...),
    fin: datetime = Form(...),
    texto: Optional[str] = Form(None),
    imagen: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    b = db.query(Banner).filter(Banner.id == banner_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Banner no encontrado.")
    if tipo not in ("texto", "imagen"):
        raise HTTPException(status_code=422, detail="tipo debe ser 'texto' o 'imagen'.")
    if audiencia not in ("todos", "vip"):
        raise HTTPException(status_code=422, detail="audiencia debe ser 'todos' o 'vip'.")
    if fin <= inicio:
        raise HTTPException(status_code=422, detail="La fecha de fin debe ser posterior al inicio.")

    b.tipo = tipo
    b.audiencia = audiencia
    b.inicio = inicio
    b.fin = fin

    if tipo == "texto":
        if not texto or not texto.strip():
            raise HTTPException(status_code=422, detail="El campo 'texto' es requerido para tipo 'texto'.")
        b.texto = texto
        b.imagen_data = None
        b.imagen_mime = None
    else:
        if imagen:
            imagen_data = await imagen.read()
            imagen_mime = imagen.content_type or ""
            _validar_imagen(imagen_data, imagen_mime)
            b.imagen_data = imagen_data
            b.imagen_mime = imagen_mime
        b.texto = None

    db.commit()
    db.refresh(b)
    return _to_out(b)


@router.patch("/{banner_id}/toggle", response_model=BannerOut)
def toggle_banner(
    banner_id: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    b = db.query(Banner).filter(Banner.id == banner_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Banner no encontrado.")
    b.activo = not b.activo
    db.commit()
    db.refresh(b)
    return _to_out(b)


@router.delete("/{banner_id}", status_code=204)
def delete_banner(
    banner_id: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_platform_user),
):
    b = db.query(Banner).filter(Banner.id == banner_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Banner no encontrado.")
    db.delete(b)
    db.commit()
