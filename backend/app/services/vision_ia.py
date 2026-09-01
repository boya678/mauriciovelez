"""Servicio compartido para análisis de imágenes con Azure OpenAI Vision."""
import json
import re
import unicodedata

from app.core.config import settings


def _normalizar(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sin_tildes.upper().strip()


def _nombres_destino_validos() -> list[str]:
    return [_normalizar(n) for n in settings.CUENTA_DESTINO_NOMBRES.split(",") if n.strip()]


def _validar_destino(numero_destino: str | None, nombre_destino: str | None) -> bool:
    """Verificación determinística: el destino debe corresponder al número Y al nombre
    de la cuenta autorizada. Si algún dato no se pudo extraer, se considera no válido
    (queda para validación manual)."""
    if not numero_destino or not nombre_destino:
        return False

    digitos = re.sub(r"\D", "", numero_destino)
    numero_ok = digitos[-10:] == settings.CUENTA_DESTINO_NUMERO

    nombre_norm = _normalizar(nombre_destino)
    nombre_ok = any(n in nombre_norm for n in _nombres_destino_validos())

    return numero_ok and nombre_ok


def analizar_imagen_con_ia(base64_img: str, mime_type: str) -> dict:
    """
    Llama a Azure OpenAI Vision y retorna:
        {"es_comprobante": bool, "comprobante_num": str|None, "monto": float|None,
         "numero_destino": str|None, "nombre_destino": str|None, "destino_valido": bool}
    La validación de destino (número + nombre del titular) se calcula en código,
    no se confía en el juicio de la IA para esa decisión.
    Lanza excepción si falla la llamada o el JSON no es parseable.
    """
    from openai import AzureOpenAI

    client = AzureOpenAI(
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_key=settings.AZURE_OPENAI_API_KEY,
        api_version="2024-02-15-preview",
    )

    prompt = (
        "Eres un experto en comprobantes de pago colombianos (Nequi, Daviplata, Bancolombia, "
        "PSE, Efecty, Banco de Bogotá, etc.).\n\n"
        "TAREA: Determina si la imagen es un comprobante de pago o transferencia exitosa. "
        "Si lo es, extrae ÚNICAMENTE:\n"
        "1. El NÚMERO DE COMPROBANTE DE TRANSACCIÓN: es el código único que el banco o app "
        "asigna para identificar esa operación específica. Aparece etiquetado como: "
        "'No. aprobación', 'No. autorización', 'No. de referencia', 'No. de transacción', "
        "'Código de confirmación', 'Referencia', 'ID de transacción', 'Comprobante No.' o similar. "
        "IMPORTANTE — NO es: número de cuenta, número de celular, cédula, NIT, ni número de tarjeta.\n"
        "2. El MONTO TRANSFERIDO: valor numérico del dinero enviado/pagado, sin símbolos ni separadores.\n"
        "3. El NÚMERO DE CUENTA/CELULAR DESTINO: el número al que se envió el dinero "
        "(destinatario de la transferencia, NO el remitente).\n"
        "4. El NOMBRE DEL TITULAR DE LA CUENTA DESTINO: el nombre de la persona que recibe "
        "el dinero (destinatario, NO el remitente).\n\n"
        "Responde ÚNICAMENTE con este JSON exacto (sin markdown, sin texto adicional):\n"
        '{"es_comprobante": true|false, "comprobante_num": "CODIGO_O_NULL", "monto": NUMERO_O_NULL, '
        '"numero_destino": "NUMERO_O_NULL", "nombre_destino": "NOMBRE_O_NULL"}\n\n'
        "Si la imagen NO es un comprobante de pago exitoso, responde con es_comprobante=false y nulls. "
        "Si no puedes leer con certeza el número o nombre del destinatario, responde null en ese campo."
    )

    response = client.chat.completions.create(
        model=settings.AZURE_OPENAI_DEPLOYMENT,
        temperature=settings.AZURE_OPENAI_TEMPERATURE,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_img}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
        max_tokens=256,
    )

    raw = response.choices[0].message.content.strip()
    resultado = json.loads(raw)

    numero_destino = resultado.get("numero_destino") or None
    nombre_destino = resultado.get("nombre_destino") or None
    resultado["numero_destino"] = numero_destino
    resultado["nombre_destino"] = nombre_destino
    resultado["destino_valido"] = _validar_destino(numero_destino, nombre_destino)
    return resultado

