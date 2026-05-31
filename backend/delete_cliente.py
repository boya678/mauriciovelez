"""
Borra un cliente y todos sus registros asociados de la base de datos.

Uso:
    python delete_cliente.py --celular 3001234567
    python delete_cliente.py --celular 3001234567 --confirmar

Sin --confirmar sólo muestra qué se eliminaría (modo dry-run).
"""
import argparse
import sys

from sqlalchemy import text

from app.database import SessionLocal
from app.models.cliente import Cliente
from app.models.numbers_historic import NumberHistoric
from app.models.suscripcion import Suscripcion
from app.models.referido import Referido
from app.models.numbers_users import NumberUser


def main() -> None:
    parser = argparse.ArgumentParser(description="Borra un cliente por número de celular.")
    parser.add_argument("--celular", required=True, help="Número de celular del cliente a borrar")
    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="Ejecuta el borrado real. Sin este flag sólo muestra lo que se eliminaría.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        cliente = db.query(Cliente).filter(Cliente.celular == args.celular).first()
        if not cliente:
            print(f"[ERROR] No se encontró ningún cliente con celular '{args.celular}'.")
            sys.exit(1)

        # Contar registros relacionados
        n_suscripciones = db.query(Suscripcion).filter(Suscripcion.cliente_id == cliente.id).count()
        n_referidos = (
            db.query(Referido)
            .filter((Referido.referente_id == cliente.id) | (Referido.referido_id == cliente.id))
            .count()
        )
        n_numbers_users = db.query(NumberUser).filter(NumberUser.id_user == cliente.id).count()
        n_historic = db.query(NumberHistoric).filter(NumberHistoric.id_user == cliente.id).count()

        print("=" * 60)
        print(f"  Cliente encontrado")
        print("=" * 60)
        print(f"  ID        : {cliente.id}")
        print(f"  Nombre    : {cliente.nombre}")
        print(f"  Celular   : {cliente.celular}")
        print(f"  Correo    : {cliente.correo}")
        print(f"  VIP       : {cliente.vip}")
        print(f"  Habilitado: {cliente.enabled}")
        print()
        print("  Registros que se eliminarán:")
        print(f"    - suscripciones   : {n_suscripciones}")
        print(f"    - referidos       : {n_referidos}")
        print(f"    - numbers_users   : {n_numbers_users}")
        print(f"    - numbers_historic: {n_historic}  (+ numero_aciertos en cascada)")
        print("=" * 60)

        if not args.confirmar:
            print()
            print("  [DRY-RUN] Nada fue borrado.")
            print("  Agrega --confirmar para ejecutar el borrado real.")
            return

        print()
        print("  Ejecutando borrado...")

        # Borrar hijos explícitamente para evitar que SQLAlchemy intente SET NULL
        # en vez de respetar el ON DELETE CASCADE de la BD.

        deleted_historic = (
            db.query(NumberHistoric)
            .filter(NumberHistoric.id_user == cliente.id)
            .delete(synchronize_session=False)
        )
        print(f"  ✓ numbers_historic eliminados : {deleted_historic}")

        deleted_nu = (
            db.query(NumberUser)
            .filter(NumberUser.id_user == cliente.id)
            .delete(synchronize_session=False)
        )
        print(f"  ✓ numbers_users eliminados    : {deleted_nu}")

        deleted_ref = (
            db.query(Referido)
            .filter((Referido.referente_id == cliente.id) | (Referido.referido_id == cliente.id))
            .delete(synchronize_session=False)
        )
        print(f"  ✓ referidos eliminados        : {deleted_ref}")

        deleted_sus = (
            db.query(Suscripcion)
            .filter(Suscripcion.cliente_id == cliente.id)
            .delete(synchronize_session=False)
        )
        print(f"  ✓ suscripciones eliminadas    : {deleted_sus}")

        db.delete(cliente)
        db.commit()

        print(f"  ✓ Cliente '{args.celular}' eliminado exitosamente.")

    except Exception as exc:
        db.rollback()
        print(f"[ERROR] {exc}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
