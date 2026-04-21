"""
normalizar_habilitados.py
=========================
Habilita todos los clientes que tengan al menos una suscripción activa y vigente.

Uso (desde el directorio backend/, con el virtualenv activo):
    python normalizar_habilitados.py
    python normalizar_habilitados.py --dry-run
"""
import argparse
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from app.database import SessionLocal
from app.models.cliente import Cliente
from app.models.suscripcion import Suscripcion


def main(dry_run: bool) -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # Clientes con al menos una suscripción activa y no vencida
        clientes_con_sus = (
            db.query(Cliente)
            .join(Suscripcion, Suscripcion.cliente_id == Cliente.id)
            .filter(
                Suscripcion.activa == True,
                Suscripcion.fin >= now,
            )
            .distinct()
            .all()
        )

        habilitados = 0
        for c in clientes_con_sus:
            if not c.enabled:
                print(f"  → Habilitar: {c.nombre} ({c.celular})")
                if not dry_run:
                    c.enabled = True
                habilitados += 1

        if dry_run:
            print(f"\n[DRY-RUN] Se habilitarían {habilitados} cliente(s). Nada fue guardado.")
        else:
            db.commit()
            print(f"\n✔  {habilitados} cliente(s) habilitado(s).")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra, no guarda")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
