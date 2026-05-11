"""
fix_dobles_suscripciones.py
----------------------------
Encuentra clientes con más de una suscripción activa y desactiva la que
tiene menos días restantes (fin más próximo), conservando la más reciente.

Uso:
    python fix_dobles_suscripciones.py          # dry-run (solo muestra)
    python fix_dobles_suscripciones.py --apply  # aplica los cambios
"""

import sys
from datetime import datetime, timezone
from collections import defaultdict

from app.database import SessionLocal
from app.models.suscripcion import Suscripcion
from app.models.cliente import Cliente

DRY_RUN = "--apply" not in sys.argv


def main():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # Traer todas las suscripciones activas con datos del cliente
        rows = (
            db.query(Suscripcion, Cliente.nombre, Cliente.celular)
            .join(Cliente, Suscripcion.cliente_id == Cliente.id)
            .filter(Suscripcion.activa == True)
            .order_by(Suscripcion.cliente_id, Suscripcion.fin.asc())
            .all()
        )

        # Agrupar por cliente
        por_cliente: dict = defaultdict(list)
        nombres: dict = {}
        celulares: dict = {}
        for sus, nombre, celular in rows:
            por_cliente[sus.cliente_id].append(sus)
            nombres[sus.cliente_id] = nombre
            celulares[sus.cliente_id] = celular

        # Filtrar solo los que tienen más de 1 activa
        dobles = {cid: subs for cid, subs in por_cliente.items() if len(subs) > 1}

        if not dobles:
            print("✓ No se encontraron clientes con más de una suscripción activa.")
            return

        print(f"{'[DRY-RUN] ' if DRY_RUN else '[APPLY] '}Clientes con múltiples suscripciones activas: {len(dobles)}\n")
        print(f"{'Cliente':<30} {'Celular':<15} {'Sub a INACTIVAR (fin)':<25} {'Sub a CONSERVAR (fin)':<25}")
        print("-" * 100)

        total_inactivadas = 0
        for cid, subs in dobles.items():
            # subs ya viene ordenado por fin ASC → subs[0] es la de menos días
            # En caso de más de 2, inactivamos todas menos la última (fin más lejano)
            a_conservar = subs[-1]
            a_inactivar = subs[:-1]

            for s in a_inactivar:
                dias_restantes = max(0, (s.fin.replace(tzinfo=timezone.utc) if not s.fin.tzinfo else s.fin - now).days)
                fin_conservar = a_conservar.fin.strftime("%Y-%m-%d") if a_conservar.fin else "?"
                fin_inactivar = s.fin.strftime("%Y-%m-%d") if s.fin else "?"

                print(
                    f"{nombres[cid]:<30} {celulares[cid]:<15} "
                    f"{fin_inactivar} ({dias_restantes}d)       "
                    f"{fin_conservar}"
                )

                if not DRY_RUN:
                    s.activa = False
                    total_inactivadas += 1

        print()
        if DRY_RUN:
            print(f"[DRY-RUN] Se inactivarían {sum(len(s) - 1 for s in dobles.values())} suscripción(es).")
            print("Ejecuta con --apply para aplicar los cambios.")
        else:
            db.commit()
            print(f"[APPLY] {total_inactivadas} suscripción(es) inactivadas correctamente.")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
