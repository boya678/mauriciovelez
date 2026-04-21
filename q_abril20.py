import psycopg2, re

DATABASE_URL = 'postgresql://postgres:Ardilla1*@transferiadb.postgres.database.azure.com:5432/portal'
m = re.match(r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', DATABASE_URL)
user, password, host, port, dbname = m.groups()
conn = psycopg2.connect(host=host, port=int(port), dbname=dbname, user=user, password=password, sslmode='require')
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM suscripciones WHERE DATE(fin AT TIME ZONE 'America/Bogota') = '2026-04-20'")
print('Vencían el 20 de abril (total):', cur.fetchone()[0])

cur.execute("SELECT COUNT(*) FROM suscripciones WHERE DATE(fin AT TIME ZONE 'America/Bogota') = '2026-04-20' AND activa = false")
print('  - ya marcadas inactivas:', cur.fetchone()[0])

cur.execute("SELECT COUNT(*) FROM suscripciones WHERE DATE(fin AT TIME ZONE 'America/Bogota') = '2026-04-20' AND activa = true")
print('  - aún activas:', cur.fetchone()[0])

conn.close()
