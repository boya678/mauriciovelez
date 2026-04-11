"""
fix_celulares_57.py
Quita el prefijo "57" de los celulares de clientes que comiencen con esos dígitos.

Uso:
    .venv\Scripts\python.exe fix_celulares_57.py          # modo DRY-RUN (solo muestra)
    .venv\Scripts\python.exe fix_celulares_57.py --apply  # aplica los cambios
"""
import sys

from app.database import SessionLocal
from app.models.cliente import Cliente


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        clientes = (
            db.query(Cliente)
            .filter(Cliente.celular.like("57%"))
            .order_by(Cliente.nombre)
            .all()
        )

        if not clientes:
            print("No se encontraron celulares que comiencen con '57'.")
            return

        print(f"{'MODO APPLY' if apply else 'DRY-RUN'} — {len(clientes)} cliente(s) afectados:\n")
        print(f"  {'Nombre':<30}  {'Celular actual':<18}  {'Celular nuevo':<18}  Estado")
        print("  " + "-" * 80)

        ok = 0
        errores = 0

        for c in clientes:
            nuevo = c.celular[2:]  # quita los primeros 2 caracteres "57"
            if not apply:
                print(f"  {c.nombre:<30}  {c.celular:<18}  {nuevo:<18}  (dry-run)")
                continue

            try:
                c.celular = nuevo
                db.flush()
                db.commit()
                print(f"  {c.nombre:<30}  {c.celular if not apply else nuevo + ' ← ' + (c.celular):<18}  {nuevo:<18}  ✔ OK")
                ok += 1
            except Exception as e:
                db.rollback()
                # recargar el objeto para que no quede en estado inválido
                db.expire(c)
                print(f"  {c.nombre:<30}  {'':18}  {nuevo:<18}  ✘ ERROR: {e}")
                errores += 1

        if apply:
            print(f"\n  Resultado: {ok} actualizado(s), {errores} error(es).")
        else:
            print("\nℹ  Sin cambios. Para aplicar ejecuta con --apply")

    finally:
        db.close()


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    main(apply)
