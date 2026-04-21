"""
normalizar_numeros.py
─────────────────────
Actualiza el valid_until de todos los números activos en numbers_users
al fin del ciclo correcto según la lógica de ciclos fijos.

Uso:
    python normalizar_numeros.py           # aplica cambios
    python normalizar_numeros.py --dry-run # solo muestra, no guarda
"""
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, ".")

from app.database import SessionLocal
from app.models.numbers_users import NumberUser
from app.models.parametro import Parametro

COLOMBIA_TZ = ZoneInfo("America/Bogota")
EPOCH_DEFAULT = date(2026, 1, 1)
VIGENCIA_FREE_DEFAULT = 10
VIGENCIA_VIP_DEFAULT = 3


def _get_param_int(db, clave: str, default: int) -> int:
    p = db.get(Parametro, clave)
    return int(p.valor) if p else default


def _get_param_date(db, clave: str, default: date) -> date:
    p = db.get(Parametro, clave)
    return date.fromisoformat(p.valor) if p else default


def calc_valid_until(vigencia: int, epoch: date, today: date) -> date:
    days_since = (today - epoch).days
    cycle = days_since // vigencia
    return epoch + timedelta(days=(cycle + 1) * vigencia)


def main(dry_run: bool) -> None:
    db = SessionLocal()
    try:
        vigencia_free = _get_param_int(db, "vigencia_free", VIGENCIA_FREE_DEFAULT)
        vigencia_vip  = _get_param_int(db, "vigencia_vip",  VIGENCIA_VIP_DEFAULT)
        epoch         = _get_param_date(db, "epoch_numeros", EPOCH_DEFAULT)
        today         = datetime.now(COLOMBIA_TZ).date()

        print(f"Epoch: {epoch}  |  Vigencia free: {vigencia_free}d  |  Vigencia VIP: {vigencia_vip}d")
        print(f"Hoy (Colombia): {today}")

        expected_free = calc_valid_until(vigencia_free, epoch, today)
        expected_vip  = calc_valid_until(vigencia_vip,  epoch, today)
        print(f"valid_until correcto → free: {expected_free}  |  VIP: {expected_vip}")
        print()

        rows = db.query(NumberUser).all()
        actualizados = 0

        for row in rows:
            expected = expected_vip if row.type == "vip" else expected_free
            if row.valid_until != expected:
                print(
                    f"  [{row.type.upper()}] id_user={row.id_user} "
                    f"number={row.number}  {row.valid_until} → {expected}"
                )
                if not dry_run:
                    row.valid_until = expected
                actualizados += 1

        if actualizados == 0:
            print("Todos los números ya tienen el valid_until correcto.")
        else:
            print(f"\nTotal a actualizar: {actualizados} registro(s)")
            if dry_run:
                print("Modo --dry-run: no se guardaron cambios.")
            else:
                db.commit()
                print("Cambios guardados.")

    except Exception:
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run)
