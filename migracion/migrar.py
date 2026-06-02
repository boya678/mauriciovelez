"""
Migración de base de datos PostgreSQL usando pg_dump + psql.
Uso:
    python migrar.py --src "postgresql://user:pass@host1:5432/db" \
                     --dst "postgresql://user:pass@host2:5432/db"

O con variables de entorno:
    set SRC_DB=postgresql://...
    set DST_DB=postgresql://...
    python migrar.py
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

PG_BIN = Path(r"C:\pgsql\pgsql\bin")
PG_DUMP = str(PG_BIN / "pg_dump.exe")
PSQL    = str(PG_BIN / "psql.exe")


def run(src: str, dst: str, clean: bool = False) -> None:
    print(f"[1/3] Haciendo dump de la base de datos origen...")
    dump_cmd = [
        PG_DUMP,
        "--no-owner",
        "--no-acl",
        "--verbose",
    ]
    if clean:
        # Incluye DROP ... IF EXISTS antes de cada objeto (funciona con todos los schemas)
        dump_cmd += ["--clean", "--if-exists"]
    dump_cmd.append(src)

    dump = subprocess.run(dump_cmd, capture_output=True)
    if dump.returncode != 0:
        print("ERROR en pg_dump:")
        print(dump.stderr.decode(errors="replace"))
        sys.exit(1)
    print(f"      Dump OK ({len(dump.stdout):,} bytes)")

    print(f"[2/3] Restaurando en base de datos destino...")
    psql_cmd = [PSQL, dst]

    result = subprocess.run(psql_cmd, input=dump.stdout, capture_output=True)
    stderr = result.stderr.decode(errors="replace")

    # psql imprime advertencias en stderr aunque todo salga bien
    errors = [l for l in stderr.splitlines() if "ERROR" in l]
    if errors:
        print("Advertencias / errores durante la restauración:")
        for e in errors:
            print("  ", e)

    if result.returncode != 0:
        print("FALLO en psql. Salida completa de stderr:")
        print(stderr)
        sys.exit(1)

    print(f"[3/3] Migración completada.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migra una BD PostgreSQL entre dos connection strings.")
    parser.add_argument("--src", default=os.getenv("SRC_DB"), help="Connection string origen")
    parser.add_argument("--dst", default=os.getenv("DST_DB"), help="Connection string destino")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Borra el schema público en destino antes de restaurar (DROP SCHEMA public CASCADE)",
    )
    args = parser.parse_args()

    if not args.src:
        parser.error("Falta --src o variable de entorno SRC_DB")
    if not args.dst:
        parser.error("Falta --dst o variable de entorno DST_DB")

    if args.src == args.dst:
        parser.error("El origen y destino son iguales")

    print("=" * 60)
    print("  MIGRACIÓN POSTGRESQL")
    print(f"  SRC: {args.src.split('@')[-1]}")   # no imprime la contraseña
    print(f"  DST: {args.dst.split('@')[-1]}")
    print("=" * 60)

    run(args.src, args.dst, clean=args.clean)


if __name__ == "__main__":
    main()
