import psycopg2
import psycopg2.extras

conn = psycopg2.connect(
    host='transferiadb.postgres.database.azure.com',
    port=5432,
    dbname='portal',
    user='postgres',
    password='Ardilla1*',
    sslmode='require'
)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Reactivar la suscripción que vence el 21/05/2026
cur.execute("""
    UPDATE public.suscripciones
    SET activa = True
    WHERE id = '4215743d-f357-4a3a-8bd6-bfba3488a270'
    RETURNING id, inicio, fin, activa
""")
updated = cur.fetchone()
conn.commit()
print("Suscripción actualizada:", dict(updated))

# Verificar estado final del cliente
cur.execute("""
    SELECT c.celular, c.vip, c.enabled, s.fin, s.activa
    FROM public.clientes c
    JOIN public.suscripciones s ON s.cliente_id = c.id
    WHERE c.celular = '3134302012'
    ORDER BY s.fin DESC
""")
rows = cur.fetchall()
for r in rows:
    print(dict(r))

cur.close()
conn.close()
