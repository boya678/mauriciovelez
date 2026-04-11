"""
dummy.py — Ejecuta manualmente los crons sin tocar el scheduler.

Uso:
    py app/dummy.py                              # reasignacion + loterias fecha actual
    py app/dummy.py --fecha 2026-04-10           # loterias de una fecha concreta
    py app/dummy.py --solo numeros               # solo reasignacion
    py app/dummy.py --solo loterias              # solo loterias
"""
import sys
import os
import logging
from pathlib import Path
from datetime import date

# Resuelve el directorio backend/ (padre de app/)
_backend_dir = Path(__file__).resolve().parent.parent

# Cambia el CWD a backend/ para que pydantic encuentre .env
os.chdir(_backend_dir)

# Agrega backend/ al path para que 'app' sea importable
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

# ── Argumentos simples ────────────────────────────────────────────────────────
args = sys.argv[1:]

solo: str | None = None
fecha: date | None = None

i = 0
while i < len(args):
    if args[i] == "--solo" and i + 1 < len(args):
        solo = args[i + 1]
        i += 2
    elif args[i] == "--fecha" and i + 1 < len(args):
        fecha = date.fromisoformat(args[i + 1])
        i += 2
    else:
        i += 1

# ── Importar las funciones internas del scheduler ────────────────────────────
from datetime import date
from app.database import SessionLocal
from app.core.scheduler import _reasignar_numeros_vencidos, _procesar_loterias

# ── Correr ───────────────────────────────────────────────────────────────────
if solo is None or solo == "numeros":
    print("\n▶  Reasignando números vencidos...")
    _reasignar_numeros_vencidos()
    print("✔  Reasignación completada.")

if solo is None or solo == "loterias":
    label = str(fecha) if fecha else "hoy"
    print(f"\n▶  Procesando loterias ({label})...")
    _procesar_loterias(fecha)
    print("✔  Loterias procesadas.")

print("\nDone.\n")
