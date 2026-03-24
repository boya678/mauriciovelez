"""
recalcular_aciertos.py  —  CLEAN SLATE
=======================================
1. Borra COMPLETAMENTE numero_aciertos y loteria_resultados.
2. Determina el rango de fechas: min(numbers_users.date_assigned) → hoy.
3. Llama la API para CADA día del rango e inserta los resultados frescos.
4. Recalcula todos los aciertos con las reglas vigentes.

Uso (desde el directorio backend/, con el virtualenv activo):
    python recalcular_aciertos.py
    python recalcular_aciertos.py --dry-run   # muestra lo que haría sin tocar la BD
"""
import argparse
import sys
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

# Asegura que el módulo app/ sea encontrable cuando se corre desde backend/
sys.path.insert(0, ".")

import httpx
from sqlalchemy import func

from app.database import SessionLocal
from app.models.loteria_resultado import LoteriaResultado
from app.models.numero_acierto import NumeroAcierto
from app.models.numbers_historic import NumberHistoric
from app.models.numbers_users import NumberUser

LOTERIAS_API = "https://api-resultadosloterias.com/api/results"


# ── Reglas de clasificación (idénticas al scheduler) ─────────────────────────

def _clasificar(numero: str, resultado: str) -> list[str]:
    """
    Devuelve el tipo de acierto con mayor jerarquía, o lista vacía si no hay.
    - exacto:           los 4 dígitos coinciden
    - directo_devuelto: primer dígito igual + últimos 3 en orden inverso
    - tres_orden:       últimos 3 dígitos iguales en orden
    - tres_desorden:    últimos 3 dígitos en orden inverso
    """
    n4 = numero.zfill(4)[-4:]
    r4 = resultado.zfill(4)[-4:]
    n3 = n4[-3:]
    r3 = r4[-3:]
    r3_rev = r3[::-1]

    if n4 == r4:
        return ["exacto"]
    if n4[0] == r4[0] and n3 == r3_rev:
        return ["directo_devuelto"]
    if n3 == r3:
        return ["tres_orden"]
    if n3 == r3_rev:
        return ["tres_desorden"]
    return []


# ── Fetch resultados de la API (tabla ya vacía → solo inserts) ────────────────

def _fetch_e_insertar(db, fecha: date, dry_run: bool) -> int:
    """Llama la API para `fecha` e inserta los resultados en loteria_resultados.
    La tabla está vacía antes de llamar esto, así que no hay conflictos."""
    fecha_str = fecha.strftime("%Y-%m-%d")
    try:
        resp = httpx.get(f"{LOTERIAS_API}/{fecha_str}", timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as exc:
        print(f"      ⚠  Error API {fecha_str}: {exc}")
        return 0

    if not data:
        return 0

    count = 0
    seen_slugs: set[str] = set()
    for item in data:
        slug = item.get("slug", "")
        if "5ta-" in slug:
            continue  # ignorar loterías de quinta (serie adicional)
        if slug in seen_slugs:
            continue  # la API a veces devuelve duplicados para el mismo slug/fecha
        seen_slugs.add(slug)
        raw_result = item.get("result", "")
        resultado_limpio = (
            raw_result[:-1] if len(raw_result) == 5 and raw_result.isdigit() else raw_result
        )
        if not dry_run:
            db.add(LoteriaResultado(
                id=uuid.uuid4(),
                fecha=fecha,
                loteria=item.get("lottery", slug),
                slug=slug,
                resultado=resultado_limpio,
                serie=item.get("series", ""),
                fetched_at=datetime.now(timezone.utc),
            ))
        count += 1

    return count


# ── Main ──────────────────────────────────────────────────────────────────────

def main(dry_run: bool) -> None:
    db = SessionLocal()
    try:
        today = date.today()

        # ── 1. Determinar rango de fechas ─────────────────────────────────────
        min_fecha = db.query(func.min(NumberUser.date_assigned)).scalar()
        if min_fecha is None:
            print("No hay registros en numbers_users. Nada que hacer.")
            return
        todas_las_fechas = []
        d = min_fecha
        while d <= today:
            todas_las_fechas.append(d)
            d += timedelta(days=1)
        print(f"Rango de fechas: {min_fecha} → {today}  ({len(todas_las_fechas):,} días)")

        # ── 2. Limpiar tablas ─────────────────────────────────────────────────
        n_aciertos = db.query(NumeroAcierto).count()
        n_resultados = db.query(LoteriaResultado).count()
        if dry_run:
            print(f"\n[DRY-RUN] Se eliminarían {n_aciertos:,} filas de numero_aciertos")
            print(f"[DRY-RUN] Se eliminarían {n_resultados:,} filas de loteria_resultados")
        else:
            print(f"\nEliminando {n_aciertos:,} filas de numero_aciertos...", end=" ", flush=True)
            db.query(NumeroAcierto).delete(synchronize_session=False)
            db.flush()
            print("OK")

            print(f"Eliminando {n_resultados:,} filas de loteria_resultados...", end=" ", flush=True)
            db.query(LoteriaResultado).delete(synchronize_session=False)
            db.commit()
            print("OK")

        # ── 3. Fetch API para cada fecha ──────────────────────────────────────
        print(f"\nConsultando API para {len(todas_las_fechas):,} fecha(s)...")
        total_api = 0
        for i, f in enumerate(todas_las_fechas, 1):
            n = _fetch_e_insertar(db, f, dry_run)
            status = f"{n} resultados" if n else "sin datos"
            print(f"  [{i:>4}/{len(todas_las_fechas)}] {f}  →  {status}")
            total_api += n
            # Commit cada 30 días para no acumular demasiado en memoria
            if not dry_run and i % 30 == 0:
                db.commit()

        if not dry_run:
            db.commit()
        print(f"  Total resultados obtenidos de API: {total_api:,}")

        # ── 4. Cargar datos para recalculo ────────────────────────────────────
        print("\nCargando datos para recalculo...")
        historicos = db.query(NumberHistoric).all()
        print(f"  numbers_historic   : {len(historicos):,}")
        users = db.query(NumberUser).all()
        print(f"  numbers_users      : {len(users):,}")
        resultados = db.query(LoteriaResultado).all()
        print(f"  loteria_resultados : {len(resultados):,}")

        # ── 5. Índices en memoria ─────────────────────────────────────────────
        # (id_user, number, date_assigned) → NumberUser
        nu_index: dict[tuple, NumberUser] = {
            (str(nu.id_user), nu.number, nu.date_assigned): nu
            for nu in users
        }
        # fecha → [LoteriaResultado]
        resultados_por_fecha: dict[date, list] = defaultdict(list)
        for r in resultados:
            resultados_por_fecha[r.fecha].append(r)

        # ── 6. Recalcular aciertos ────────────────────────────────────────────
        print("Recalculando aciertos...")
        nuevos = 0
        sin_vigencia = 0

        for h in historicos:
            key = (str(h.id_user), h.number, h.date)
            nu = nu_index.get(key)
            if nu is None:
                sin_vigencia += 1
                continue

            for fecha, lista_resultados in resultados_por_fecha.items():
                if not (nu.date_assigned <= fecha <= nu.valid_until):
                    continue
                for resultado in lista_resultados:
                    for tipo in _clasificar(h.number, resultado.resultado):
                        if not dry_run:
                            db.add(NumeroAcierto(
                                id=uuid.uuid4(),
                                historic_id=h.id,
                                resultado_id=resultado.id,
                                tipo=tipo,
                                created_at=datetime.now(timezone.utc),
                            ))
                        nuevos += 1

        if not dry_run:
            db.commit()

        prefix = "[DRY-RUN] " if dry_run else ""
        print(f"\n{prefix}Resultado final:")
        print(f"  Rango consultado             : {min_fecha} → {today}")
        print(f"  Días consultados             : {len(todas_las_fechas):,}")
        print(f"  Resultados de API obtenidos  : {total_api:,}")
        print(f"  Aciertos insertados          : {nuevos:,}")
        print(f"  Sin registro vigencia        : {sin_vigencia:,}")
        if dry_run:
            print("\n[DRY-RUN] No se realizaron cambios en la BD.")
        else:
            print("\nRecalculo completado exitosamente.")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recalcula la tabla numero_aciertos (clean slate)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra lo que haría sin modificar la base de datos",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
