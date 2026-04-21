import time
import openpyxl
import httpx

EXCEL_PATH = r'c:\Users\boya6\OneDrive\Documents\maxibingo\mauriciovelez\CONTROL VIP (1).xlsx'
BASE_URL   = 'https://api.mauricioveleznumerologo.com'
TOKEN      = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJjNTFlZDMwYy1lZTU1LTQ4NjQtOGM1ZS0wMWEyZWZmNWE3NzQiLCJyb2xlIjoiYWRtaW4iLCJleHAiOjE3NzY4MDc4MzksImlzcyI6ImFkbWluIn0.LgbJCKub5srJjHzfPo4BjfalHXMOq7GhkmIn0M_9Ypo'

HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}

wb = openpyxl.load_workbook(EXCEL_PATH)
ws = wb.active

COL_SUS_ID = 5  # E

# Recopilar IDs únicos no vacíos
ids = []
for row in ws.iter_rows(min_row=2):
    val = row[COL_SUS_ID - 1].value
    if val and str(val).strip():
        sus_id = str(val).strip()
        if sus_id not in ids:
            ids.append(sus_id)

print(f"Total suscripciones a renovar: {len(ids)}\n")

ok = 0
errores = 0

for i, sus_id in enumerate(ids, 1):
    url = f'{BASE_URL}/admin/suscripciones/{sus_id}/renovar'
    try:
        resp = httpx.post(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            print(f"[{i}/{len(ids)}] ✔  {sus_id[:8]}... → {data.get('nombre', '')} ({data.get('celular', '')})")
            ok += 1
        else:
            print(f"[{i}/{len(ids)}] ✗  {sus_id[:8]}... → HTTP {resp.status_code}: {resp.text[:100]}")
            errores += 1
    except Exception as e:
        print(f"[{i}/{len(ids)}] ✗  {sus_id[:8]}... → Error: {e}")
        errores += 1

    # Pequeña pausa para no saturar el servidor
    time.sleep(0.1)

print(f"\n✔  Renovaciones exitosas : {ok}")
print(f"✗  Errores               : {errores}")
