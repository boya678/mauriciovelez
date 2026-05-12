"""
Script independiente: carga el pool de números desde el Excel al la tabla numbers.

Uso:
    python load_numbers.py

- Trunca la tabla numbers.
- Inserta los 2520 números en el orden exacto del Excel (order_index 1..2520).
- No toca ninguna otra tabla.
"""
import os
import sys
from pathlib import Path

import openpyxl
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# ── Cargar .env ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]
EXCEL_PATH = BASE_DIR.parent / "Numero de la quincena 4 cifras sin numero reflejo.xlsx"

# ── Leer Excel ────────────────────────────────────────────────────────────────
print(f"Leyendo Excel: {EXCEL_PATH}")
wb = openpyxl.load_workbook(EXCEL_PATH)
ws = wb["mauricio 2"]

raw = [row[0] for row in ws.iter_rows(values_only=True) if row[0] is not None]

if not raw:
    print("ERROR: No se encontraron números en el Excel.")
    sys.exit(1)

# Validación básica
invalidos = [n for n in raw if not (isinstance(n, str) and len(n) == 4 and n.isdigit())]
if invalidos:
    print(f"ERROR: Números inválidos (no son 4 dígitos): {invalidos[:10]}")
    sys.exit(1)

# Deduplicar preservando el orden del Excel
seen = set()
numeros = []
for n in raw:
    if n not in seen:
        seen.add(n)
        numeros.append(n)

duplicados = len(raw) - len(numeros)
if duplicados:
    print(f"Advertencia: se eliminaron {duplicados} duplicados del Excel.")

print(f"Números en Excel: {len(raw)} | Únicos a cargar: {len(numeros)}")
print(f"Primeros 5: {numeros[:5]}")
print(f"Últimos 5:  {numeros[-5:]}")

# ── Cargar a BD ───────────────────────────────────────────────────────────────
print(f"\nConectando a la BD...")
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = False
try:
    with conn.cursor() as cur:
        print("Truncando tabla numbers...")
        cur.execute("TRUNCATE TABLE numbers")

        print("Insertando números (bulk)...")
        rows = [(n, False, idx + 1) for idx, n in enumerate(numeros)]
        execute_values(
            cur,
            "INSERT INTO numbers (number, assigned, order_index) VALUES %s",
            rows,
            page_size=500,
        )

    conn.commit()
    print(f"\nListo. {len(numeros)} números cargados correctamente.")
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
