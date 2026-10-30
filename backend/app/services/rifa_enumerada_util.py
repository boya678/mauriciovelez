"""Utilidades puras (sin BD) del servicio 'Rifa enumerada': dibujar la boleta y leer el Excel."""
import io
import re
from pathlib import Path

import openpyxl
from PIL import Image, ImageDraw, ImageFont, ImageOps

FUENTE_NEGRITA = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "DejaVuSans-Bold.ttf"
MAX_ANCHO = 1600           # límite para que la imagen final pese poco (WhatsApp admite 5 MB)
FRANJA_PROPORCION = 0.14   # alto de la franja negra respecto al alto de la imagen
FRANJA_MIN = 60
TEXTO_PROPORCION = 0.62    # alto del número respecto al alto de la franja
TEXTO_MAX_ANCHO = 0.8      # el número nunca ocupa más de este porcentaje del ancho

CELULAR_RE = re.compile(r"^57\d{10}$")
MAX_FILAS = 20000


def _fuente(tamano: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FUENTE_NEGRITA), tamano)
    except OSError:
        return ImageFont.load_default(size=tamano)


def render_boleta(base: bytes, numero: str) -> bytes:
    """Devuelve un JPG: la imagen base con una franja negra abajo y el número en blanco y negrita."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(base))).convert("RGB")
    if img.width > MAX_ANCHO:
        alto = round(img.height * MAX_ANCHO / img.width)
        img = img.resize((MAX_ANCHO, alto), Image.LANCZOS)

    ancho, alto = img.size
    franja = max(FRANJA_MIN, round(alto * FRANJA_PROPORCION))

    lienzo = Image.new("RGB", (ancho, alto + franja), (0, 0, 0))
    lienzo.paste(img, (0, 0))

    tamano = max(10, round(franja * TEXTO_PROPORCION))
    dibujo = ImageDraw.Draw(lienzo)
    fuente = _fuente(tamano)
    caja = dibujo.textbbox((0, 0), numero, font=fuente)
    while (caja[2] - caja[0]) > ancho * TEXTO_MAX_ANCHO and tamano > 10:
        tamano -= 2
        fuente = _fuente(tamano)
        caja = dibujo.textbbox((0, 0), numero, font=fuente)

    x = (ancho - (caja[2] - caja[0])) / 2 - caja[0]
    y = alto + (franja - (caja[3] - caja[1])) / 2 - caja[1]
    dibujo.text((x, y), numero, font=fuente, fill=(255, 255, 255))

    salida = io.BytesIO()
    lienzo.save(salida, format="JPEG", quality=90, optimize=True)
    return salida.getvalue()


def leer_celulares(datos: bytes) -> dict:
    """Primera hoja, primera columna, sin la cabecera. Normaliza, quita duplicados e inválidos.

    Retorna {"total_filas", "validas": [str], "invalidas": [{"fila", "valor"}], "duplicadas": int}.
    """
    libro = openpyxl.load_workbook(io.BytesIO(datos), read_only=True, data_only=True)
    try:
        hoja = libro.worksheets[0]
        validas: list[str] = []
        vistos: set[str] = set()
        invalidas: list[dict] = []
        duplicadas = 0
        filas = 0
        for numero_fila, fila in enumerate(hoja.iter_rows(min_row=2, max_col=1, values_only=True), start=2):
            valor = fila[0] if fila else None
            if valor is None or (isinstance(valor, str) and not valor.strip()):
                continue
            filas += 1
            if filas > MAX_FILAS:
                raise ValueError(f"El Excel supera el máximo de {MAX_FILAS} filas")
            if isinstance(valor, float) and valor.is_integer():
                valor = int(valor)
            digitos = re.sub(r"\D", "", str(valor))
            if len(digitos) == 10 and digitos.startswith("3"):
                digitos = "57" + digitos
            if not CELULAR_RE.match(digitos):
                invalidas.append({"fila": numero_fila, "valor": str(valor)[:40]})
                continue
            if digitos in vistos:
                duplicadas += 1
                continue
            vistos.add(digitos)
            validas.append(digitos)
        return {"total_filas": filas, "validas": validas, "invalidas": invalidas, "duplicadas": duplicadas}
    finally:
        libro.close()
