"""
actualizar_fin_suscripciones.py
Actualiza el campo `fin` de cada suscripción activa (col E) al valor de col D + 1 mes.

Uso:
    py actualizar_fin_suscripciones.py            # aplica cambios
    py actualizar_fin_suscripciones.py --dry-run  # solo muestra, no modifica
"""
import sys
import psycopg2
import re
import openpyxl
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta

DRY_RUN = '--dry-run' in sys.argv

DATABASE_URL = 'postgresql://postgres:Ardilla1*@transferiadb.postgres.database.azure.com:5432/portal'
m = re.match(r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', DATABASE_URL)
user, password, host, port, dbname = m.groups()

conn = psycopg2.connect(host=host, port=int(port), dbname=dbname, user=user, password=password, sslmode='require')
cur = conn.cursor()

EXCEL_PATH = r'c:\Users\boya6\OneDrive\Documents\maxibingo\mauriciovelez\CONTROL VIP (1).xlsx'
wb = openpyxl.load_workbook(EXCEL_PATH)
ws = wb.active

COL_FECHA_D  = 4   # D — fecha base
COL_SUS_ID   = 5   # E — suscripcion_id activa

print(f"{'[DRY RUN] ' if DRY_RUN else ''}Procesando...\n")

procesados = actualizados = sin_id = sin_fecha = errores = 0

for row in ws.iter_rows(min_row=2):
    sus_id = row[COL_SUS_ID - 1].value
    fecha_raw = row[COL_FECHA_D - 1].value

    if not sus_id or not str(sus_id).strip():
        sin_id += 1
        continue

    if not fecha_raw:
        sin_fecha += 1
        continue

    sus_id = str(sus_id).strip()

    # Parsear fecha col D (puede ser datetime de Excel o string dd/mm/aaaa)
    try:
        if isinstance(fecha_raw, datetime):
            fecha_d = fecha_raw.date()
        else:
            fecha_d = datetime.strptime(str(fecha_raw).strip(), '%d/%m/%Y').date()
    except Exception:
        print(f"  ✗  No se pudo parsear fecha '{fecha_raw}' para {sus_id[:8]}...")
        errores += 1
        continue

    nuevo_fin = datetime(
        fecha_d.year, fecha_d.month, fecha_d.day,
        tzinfo=timezone.utc
    ) + relativedelta(months=1)

    print(f"  {'[DRY]' if DRY_RUN else '     '} {sus_id[:8]}... → fin: {fecha_d.strftime('%d/%m/%Y')} + 1 mes = {nuevo_fin.strftime('%d/%m/%Y')}")

    if not DRY_RUN:
        try:
            cur.execute(
                "UPDATE suscripciones SET fin = %s WHERE id = %s",
                (nuevo_fin, sus_id)
            )
            if cur.rowcount == 0:
                print(f"           ⚠  No se encontró suscripción con id {sus_id}")
                errores += 1
            else:
                actualizados += 1
        except Exception as e:
            print(f"           ✗  Error al actualizar {sus_id}: {e}")
            conn.rollback()
            errores += 1
            continue

    procesados += 1

if not DRY_RUN:
    conn.commit()
    print(f"\n✔  Commit realizado")

cur.close()
conn.close()

print(f"\n{'[DRY RUN] ' if DRY_RUN else ''}Resumen:")
print(f"   Filas procesadas   : {procesados}")
print(f"   Actualizadas       : {actualizados if not DRY_RUN else procesados}")
print(f"   Sin ID (col E)     : {sin_id}")
print(f"   Sin fecha (col D)  : {sin_fecha}")
print(f"   Errores            : {errores}")
