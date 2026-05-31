"""
Lista y corrige los codigo_vip atípicos de tipo_cliente=1.
Atípico = numérico puro con valor > 9000 O con más de 5 dígitos.
Los reemplaza por el siguiente valor en secuencia a partir del max normal + 1.
"""
import sys
sys.path.insert(0, '.')
from app.core.config import settings
from sqlalchemy import create_engine, text

engine = create_engine(settings.DATABASE_URL)

REGEX_SOLO_NUMEROS = "^[0-9]+$"

with engine.begin() as conn:
    # --- 1. Buscar atípicos ---
    atipicos = conn.execute(text(
        "SELECT id, nombre, celular, codigo_vip "
        "FROM clientes "
        "WHERE tipo_cliente = 1 "
        "  AND codigo_vip IS NOT NULL "
        "  AND codigo_vip ~ :regex "
        "  AND (LENGTH(codigo_vip) > 5 OR codigo_vip::bigint > 9000) "
        "ORDER BY codigo_vip::bigint DESC"
    ), {"regex": REGEX_SOLO_NUMEROS}).fetchall()

    # --- 2. Max del rango normal ---
    max_normal = conn.execute(text(
        "SELECT MAX(codigo_vip::bigint) "
        "FROM clientes "
        "WHERE tipo_cliente = 1 "
        "  AND codigo_vip IS NOT NULL "
        "  AND codigo_vip ~ :regex "
        "  AND LENGTH(codigo_vip) <= 5 "
        "  AND codigo_vip::bigint <= 9000"
    ), {"regex": REGEX_SOLO_NUMEROS}).scalar()

    siguiente = max_normal + 1

    print(f"Aplicando corrección a {len(atipicos)} registros (max normal={max_normal}):\n")
    for r in atipicos:
        nuevo_codigo = f"{siguiente:05d}"
        conn.execute(text(
            "UPDATE clientes SET codigo_vip = :nuevo WHERE id = :id"
        ), {"nuevo": nuevo_codigo, "id": r[0]})
        print(f"  {r[3]:>8}  ->  {nuevo_codigo}  ({r[1][:25]})")
        siguiente += 1

    print(f"\nHecho. Secuencia futura VIP arranca en: {siguiente:05d} ({siguiente})")
