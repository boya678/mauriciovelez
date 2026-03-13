"""
Script 1: Lee numeros.users y genera inserts_clientes.sql
Ejecutar: .venv\Scripts\python.exe migrate_users.py
"""
import psycopg2

conn = psycopg2.connect(
    host="transferiadb.postgres.database.azure.com",
    database="numeros",
    user="postgres",
    password="Ardilla1*",
    port=5432,
    sslmode="require",
)
cur = conn.cursor()
cur.execute("SELECT id, phone, username, balance FROM users ORDER BY username")
rows = cur.fetchall()
cur.close()
conn.close()
print(f"Usuarios leidos: {len(rows)}")

skipped = 0
lines = []
for user_id, phone, username, balance in rows:
    celular = (phone or "").strip().replace("'", "''")
    if not celular:
        skipped += 1
        continue
    nombre = (username or "").strip().replace("'", "''") or "Sin nombre"
    saldo = float(balance) if balance is not None else 0.0
    lines.append(
        f"INSERT INTO clientes (id, nombre, celular, saldo, vip) "
        f"VALUES ('{user_id}', '{nombre}', '{celular}', {saldo}, false) "
        f"ON CONFLICT (celular) DO NOTHING;"
    )

out = "inserts_clientes.sql"
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Inserts generados: {len(lines)}")
print(f"Omitidos (celular vacio): {skipped}")
print(f"Archivo: {out}")


DB_ORIGIN = dict(
    host="transferiadb.postgres.database.azure.com",
    database="numeros",
    user="postgres",
    password="Ardilla1*",
    port=5432,
    sslmode="require",
)

DB_DEST = dict(
    host="transferiadb.postgres.database.azure.com",
    database="portal",
    user="postgres",
    password="Ardilla1*",
    port=5432,
    sslmode="require",
)

src = psycopg2.connect(**DB_ORIGIN)
dst = psycopg2.connect(**DB_DEST)

src_cur = src.cursor()
dst_cur = dst.cursor()

src_cur.execute("SELECT id, phone, username, balance FROM users ORDER BY username")
rows = src_cur.fetchall()
print(f"Usuarios en origen: {len(rows)}")

batch = []
skipped = 0

for user_id, phone, username, balance in rows:
    saldo = balance if balance is not None else 0
    nombre = (username or "").strip() or "Sin nombre"
    celular = (phone or "").strip()

    if not celular:
        skipped += 1
        continue

    batch.append((str(user_id), nombre, celular, saldo))

dst_cur.executemany(
    """
    INSERT INTO clientes (id, nombre, celular, saldo, vip)
    VALUES (%s, %s, %s, %s, false)
    ON CONFLICT (celular) DO NOTHING
    """,
    batch,
)
dst.commit()

inserted = dst_cur.rowcount
print(f"Procesados: {len(batch)}")
print(f"Omitidos (celular vacio): {skipped}")

src_cur.close(); src.close()
dst_cur.close(); dst.close()
print("Migracion completada.")
