"""
Borra un cliente y todos sus datos asociados de la base de datos.

Tablas afectadas (en orden):
  1. numero_aciertos    — via numbers_historic.id
  2. numbers_historic   — via id_user (sin FK CASCADE)
  3. numbers_users      — CASCADE desde clientes
  4. suscripciones      — CASCADE desde clientes
  5. contactos          — CASCADE desde clientes
  6. clientes           — registro principal

Uso:
    python borrar_cliente.py <cliente_id>
"""

import sys
import uuid

from sqlalchemy import delete

from app.database import SessionLocal
from app.models.cliente import Cliente
from app.models.loteria_resultado import LoteriaResultado  # necesario para resolver el relationship de NumeroAcierto
from app.models.numbers_historic import NumberHistoric
from app.models.numero_acierto import NumeroAcierto


def borrar_cliente(cliente_id_str: str) -> None:
    try:
        cliente_id = uuid.UUID(cliente_id_str)
    except ValueError:
        print(f"ERROR: '{cliente_id_str}' no es un UUID válido.")
        sys.exit(1)

    db = SessionLocal()
    try:
        cliente = db.get(Cliente, cliente_id)
        if cliente is None:
            print(f"ERROR: No se encontró un cliente con id={cliente_id}")
            sys.exit(1)

        print(f"Cliente encontrado: {cliente.nombre} | {cliente.celular}")
        confirmacion = input("¿Confirmar borrado? Escriba 'si' para continuar: ").strip().lower()
        if confirmacion != "si":
            print("Operación cancelada.")
            sys.exit(0)

        # 1. Obtener IDs del histórico del cliente
        historic_ids = [
            row.id for row in
            db.query(NumberHistoric.id).filter(NumberHistoric.id_user == cliente_id).all()
        ]

        # 2. Borrar numero_aciertos asociados a esos históricos
        if historic_ids:
            deleted_aciertos = db.execute(
                delete(NumeroAcierto).where(NumeroAcierto.historic_id.in_(historic_ids))
            ).rowcount
            print(f"  numero_aciertos eliminados : {deleted_aciertos}")

        # 3. Borrar numbers_historic del cliente
        deleted_historic = db.execute(
            delete(NumberHistoric).where(NumberHistoric.id_user == cliente_id)
        ).rowcount
        print(f"  numbers_historic eliminados: {deleted_historic}")

        # 4. Borrar el cliente (numbers_users, suscripciones y contactos se eliminan por CASCADE)
        db.delete(cliente)

        db.commit()
        print(f"✓ Cliente '{cliente.nombre}' ({cliente_id}) eliminado correctamente.")

    except Exception as e:
        db.rollback()
        print(f"ERROR inesperado: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python borrar_cliente.py <cliente_id>")
        sys.exit(1)

    borrar_cliente(sys.argv[1])
