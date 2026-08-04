"""Servicio compartido para análisis de imágenes con Azure OpenAI Vision."""
import json

from app.core.config import settings


def analizar_imagen_con_ia(base64_img: str, mime_type: str) -> dict:
    """
    Llama a Azure OpenAI Vision y retorna:
        {"es_comprobante": bool, "comprobante_num": str|None, "monto": float|None}
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
        "2. El MONTO TRANSFERIDO: valor numérico del dinero enviado/pagado, sin símbolos ni separadores.\n\n"
        "Responde ÚNICAMENTE con este JSON exacto (sin markdown, sin texto adicional):\n"
        '{"es_comprobante": true|false, "comprobante_num": "CODIGO_O_NULL", "monto": NUMERO_O_NULL}\n\n'
        "Si la imagen NO es un comprobante de pago exitoso, responde con es_comprobante=false y nulls."
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
    return json.loads(raw)
