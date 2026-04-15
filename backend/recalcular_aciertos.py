"""
recalcular_aciertos.py  —  INCREMENTAL (sin notificaciones)
============================================================
Copia de la lógica de _procesar_loterias del scheduler pero SIN enviar
WhatsApp ni deshabilitar cuentas free.

Recorre cada día desde el 1 de abril de 2026 hasta hoy (Colombia):
  1. Upsert resultados de la API en loteria_resultados.
  2. Cruza con numbers_historic y crea aciertos faltantes en numero_aciertos.

Uso (desde el directorio backend/, con el virtualenv activo):
    python recalcular_aciertos.py
    python recalcular_aciertos.py --dry-run
    python recalcular_aciertos.py --desde 2026-03-15
"""
import argparse
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, ".")

import httpx
from sqlalchemy import and_

from app.database import SessionLocal
from app.models.loteria_resultado import LoteriaResultado
from app.models.numero_acierto import NumeroAcierto
from app.models.numbers_historic import NumberHistoric
from app.models.numbers_users import NumberUser

COLOMBIA_TZ = ZoneInfo("America/Bogota")
LOTERIAS_API = "https://api-resultadosloterias.com/api/results"
FECHA_INICIO_DEFAULT = date(2026, 4, 1)


def _clasificar(numero: str, resultado: str) -> list[str]:
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


def _procesar_fecha(db, fecha: date, dry_run: bool) -> tuple[int, int]:
    """
    Misma lógica que _procesar_loterias del scheduler, sin notificaciones.
    Retorna (nuevos_resultados, nuevos_aciertos).
    """
    fecha_str = fecha.strftime("%Y-%m-%d")

    # ── 1. Fetch API ──────────────────────────────────────────────────────────
    try:
        resp = httpx.get(f"{LOTERIAS_API}/{fecha_str}", timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as exc:
        print(f"      ⚠  Error API {fecha_str}: {exc}")
        return 0, 0

    if not data:
        return 0, 0

    # ── 2. Upsert resultados ──────────────────────────────────────────────────
    resultados_map: dict[str, LoteriaResultado] = {}
    seen_slugs: set[str] = set()
    nuevos_res = 0
    for item in data:
        slug = item.get("slug", "")
        if "5ta-" in slug:
            continue
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        raw_result = item.get("result", "")
        resultado_limpio = raw_result[:-1] if len(raw_result) == 5 and raw_result.isdigit() else raw_result

        existing = (
            db.query(LoteriaResultado)
            .filter(LoteriaResultado.fecha == fecha, LoteriaResultado.slug == slug)
            .first()
        )
        if existing:
            existing.resultado = resultado_limpio
            existing.fetched_at = datetime.now(timezone.utc)
            resultados_map[slug] = existing
        else:
            nuevo = LoteriaResultado(
                id=uuid.uuid4(),
                fecha=fecha,
                loteria=item.get("lottery", slug),
                slug=slug,
                resultado=resultado_limpio,
                serie=item.get("series", ""),
                fetched_at=datetime.now(timezone.utc),
            )
            if not dry_run:
                db.add(nuevo)
            resultados_map[slug] = nuevo
            nuevos_res += 1

    if not dry_run:
        db.flush()

    # ── 3. Cruce con numbers_historic (vigencia que cubra esta fecha) ─────────
    historicos = (
        db.query(NumberHistoric)
        .join(
            NumberUser,
            and_(
                NumberUser.id_user == NumberHistoric.id_user,
                NumberUser.number == NumberHistoric.number,
                NumberUser.date_assigned == NumberHistoric.date,
            ),
        )
        .filter(
            NumberUser.date_assigned <= fecha,
            NumberUser.valid_until >= fecha,
        )
        .all()
    )

    nuevos_ac = 0
    for h in historicos:
        for resultado in resultados_map.values():
            for tipo in _clasificar(h.number, resultado.resultado):
                existe = (
                    db.query(NumeroAcierto)
                    .filter(
                        NumeroAcierto.historic_id == h.id,
                        NumeroAcierto.resultado_id == resultado.id,
                        NumeroAcierto.tipo == tipo,
                    )
                    .first()
                )
                if not existe:
                    if not dry_run:
                        db.add(NumeroAcierto(
                            id=uuid.uuid4(),
                            historic_id=h.id,
                            resultado_id=resultado.id,
                            tipo=tipo,
                        ))
                    nuevos_ac += 1

    if not dry_run:
        db.commit()

    return nuevos_res, nuevos_ac


# ── Main ──────────────────────────────────────────────────────────────────────

def main(dry_run: bool, desde: date | None = None) -> None:
    today = datetime.now(COLOMBIA_TZ).date()
    inicio = desde or FECHA_INICIO_DEFAULT
    fechas = []
    d = inicio
    while d <= today:
        fechas.append(d)
        d += timedelta(days=1)

    print(f"Rango: {inicio} → {today}  ({len(fechas)} días)")
    if dry_run:
        print("[DRY-RUN] No se modificará la BD.\n")

    db = SessionLocal()
    total_res = 0
    total_ac = 0

    try:
        for i, f in enumerate(fechas, 1):
            nr, na = _procesar_fecha(db, f, dry_run)
            estado = []
            if nr:
                estado.append(f"+{nr} resultados")
            if na:
                estado.append(f"+{na} aciertos")
            info = ", ".join(estado) if estado else "sin cambios"
            print(f"  [{i:>3}/{len(fechas)}] {f}  →  {info}")
            total_res += nr
            total_ac += na

        prefix = "[DRY-RUN] " if dry_run else ""
        print(f"\n{prefix}Resumen:")
        print(f"  Días procesados        : {len(fechas)}")
        print(f"  Resultados nuevos      : {total_res}")
        print(f"  Aciertos nuevos        : {total_ac}")
        if dry_run:
            print("\nNo se realizaron cambios en la BD.")
        else:
            print("\nCompletado.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Busca resultados y aciertos faltantes (incremental, sin notificaciones)"
    )
    parser.add_argument("--dry-run", action="store_true", help="No modifica la BD")
    parser.add_argument(
        "--desde",
        type=lambda s: date.fromisoformat(s),
        default=None,
        help="Fecha inicio (YYYY-MM-DD). Default: 2026-04-01",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run, desde=args.desde)
