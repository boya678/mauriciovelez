"""
Script de prueba: analiza una imagen con Azure OpenAI Vision
y determina si es un comprobante de pago con el monto esperado.

Uso:
    python test_vision_pago.py                        # usa download (6).jpeg
    python test_vision_pago.py ruta/a/imagen.jpg      # imagen personalizada
"""
import base64
import json
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "backend" / ".env")

ENDPOINT   = os.getenv("AZURE_OPENAI_ENDPOINT", "")
API_KEY    = os.getenv("AZURE_OPENAI_API_KEY", "")
DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")
VIP_AMOUNT = int(os.getenv("VIP_AMOUNT", "30000"))

# ── Imagen a analizar ─────────────────────────────────────────────────────────
img_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "download.jpeg"

if not img_path.exists():
    print(f"[ERROR] Imagen no encontrada: {img_path}")
    sys.exit(1)

suffix = img_path.suffix.lower()
mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
mime_type = mime_map.get(suffix, "image/jpeg")

print(f"Imagen  : {img_path.name}")
print(f"Tamaño  : {img_path.stat().st_size / 1024:.1f} KB")
print(f"Modelo  : {DEPLOYMENT}")
print(f"Endpoint: {ENDPOINT}")
print(f"Monto esperado: ${VIP_AMOUNT:,}")
print("-" * 55)

# ── Codificar en base64 ───────────────────────────────────────────────────────
with open(img_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")

# ── Llamada a Azure OpenAI Vision ─────────────────────────────────────────────
from openai import AzureOpenAI

client = AzureOpenAI(
    azure_endpoint=ENDPOINT,
    api_key=API_KEY,
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

print("Enviando a la IA...")
response = client.chat.completions.create(
    model=DEPLOYMENT,
    temperature=0,
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{b64}",
                        "detail": "high",
                    },
                },
            ],
        }
    ],
    max_tokens=256,
)

raw = response.choices[0].message.content.strip()
print(f"\nRespuesta cruda : {raw}")

# ── Parsear y evaluar ─────────────────────────────────────────────────────────
try:
    data = json.loads(raw)
except json.JSONDecodeError as e:
    print(f"\n[ERROR] No se pudo parsear el JSON: {e}")
    sys.exit(1)

print("\n── Resultado ───────────────────────────────────────")
print(f"  ¿Es comprobante? : {data.get('es_comprobante')}")
print(f"  Comprobante Nro  : {data.get('comprobante_num')}")
print(f"  Monto extraído   : {data.get('monto')}")

monto = data.get("monto")
if data.get("es_comprobante") and monto is not None:
    if int(monto) == VIP_AMOUNT:
        print(f"\n✅ MONTO CORRECTO — aplicaría renovación VIP")
    else:
        print(f"\n❌ MONTO INCORRECTO — esperado ${VIP_AMOUNT:,}, encontrado ${int(monto):,}")
else:
    print("\n⚠️  No es comprobante o monto no encontrado — no aplica")

# ── Tokens usados ─────────────────────────────────────────────────────────────
usage = response.usage
print(f"\nTokens: prompt={usage.prompt_tokens} | completion={usage.completion_tokens} | total={usage.total_tokens}")
