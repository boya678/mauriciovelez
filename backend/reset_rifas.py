import sys
import psycopg2


FULL_MODE = "--full" in sys.argv


conn = psycopg2.connect(
    host='dataradb.postgres.database.azure.com',
    port=5432,
    dbname='portal',
    user='postgres',
    password='Ardilla1*',
    sslmode='require'
)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM rifa_boletas")
boletas = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM rifa_numeros")
pool = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM rifas")
rifas = cur.fetchone()[0]

if FULL_MODE:
    print(f"[FULL] Se van a eliminar: {boletas} boletas, {pool} numeros pool y {rifas} rifas.")
else:
    print(
        f"[SECUENCIAS] Se van a resetear: {boletas} boletas y {pool} numeros pool "
        f"en {rifas} rifas (respetando seq_inicio/seq_fin)."
    )

resp = input("¿Continuar? (s/N): ").strip().lower()
if resp != "s":
    print("Cancelado.")
    cur.close()
    conn.close()
    sys.exit(0)

if FULL_MODE:
    cur.execute("DELETE FROM rifa_boletas")
    cur.execute("DELETE FROM rifa_numeros")
    cur.execute("DELETE FROM rifas")
else:
    # 1) Limpiar asignaciones actuales.
    cur.execute("DELETE FROM rifa_boletas")
    cur.execute("DELETE FROM rifa_numeros")

    # 2) Re-crear pool por cada rifa existente según secuencia configurada.
    cur.execute(
        """
        INSERT INTO rifa_numeros (rifa_id, numero, orden_aleatorio, asignado)
        SELECT
            r.id,
            base.numero,
            ROW_NUMBER() OVER (PARTITION BY r.id ORDER BY random()),
            false
        FROM rifas r
        JOIN LATERAL generate_series(r.seq_inicio, r.seq_fin) AS base(numero) ON true
        """
    )

conn.commit()
print("Hecho.")

cur.close()
conn.close()
