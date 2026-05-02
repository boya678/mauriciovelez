"""Genera archivo plano con clientes que tienen más de 1 suscripción iniciada en abril 2026."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL").replace("postgresql://", "postgres://", 1) if os.getenv("DATABASE_URL", "").startswith("postgresql://") else os.getenv("DATABASE_URL")

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()
cur.execute("""
    SELECT c.id, c.nombre, c.codigo_pais, c.celular, c.correo, c.vip, COUNT(s.id) AS subs_abril
    FROM clientes c
    JOIN suscripciones s ON s.cliente_id = c.id
    WHERE s.inicio >= '2026-04-01' AND s.inicio < '2026-05-01'
    GROUP BY c.id, c.nombre, c.codigo_pais, c.celular, c.correo, c.vip
    HAVING COUNT(s.id) > 1
    ORDER BY subs_abril DESC, c.nombre;
""")
rows = cur.fetchall()
out_path = os.path.join(os.path.dirname(__file__), "..", "suscripciones_abril_multi.txt")
out_path = os.path.abspath(out_path)
with open(out_path, "w", encoding="utf-8") as f:
    f.write("id|nombre|codigo_pais|celular|correo|vip|subs_abril\n")
    for r in rows:
        f.write("|".join(str(x) for x in r) + "\n")
print(f"Total clientes: {len(rows)}")
print(f"Archivo: {out_path}")
cur.close()
conn.close()
