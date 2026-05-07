"""
Seed script: crea las 4 herramientas SQL para el tenant mauriciovelez.

Ejecutar con:
    kubectl exec -n mauriciovelez deploy/chatsystem-backend -- python /app/seed_tools_mauriciovelez.py

O localmente si tenés acceso directo a la DB:
    python seed_tools_mauriciovelez.py
"""

import asyncio
import json
import uuid
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os

DATABASE_URL = os.environ["DATABASE_URL"]
TENANT_SLUG = "mauriciovelez"

# DSN explícito del DB donde viven las tablas clientes/suscripciones/etc.
# Se almacena literalmente en la columna sql_dsn del tool; no depende de
# variables de entorno del chatsystem.
PORTAL_DB_URL = "postgresql+asyncpg://postgres:Ardilla1*@transferiadb.postgres.database.azure.com:5432/portal"

TOOLS = [
    {
        "name": "consultar_numeros_asignados",
        "description": (
            "Consulta los números de lotería asignados al usuario. "
            "Úsala cuando el usuario pregunta cuáles son sus números, "
            "qué números tiene, cuántos números le tocan, etc."
        ),
        "tool_type": "SQL",
        "sql_dsn": PORTAL_DB_URL,
        "sql_query": """
            SELECT nu.number, nu.type, nu.valid_until::text
            FROM numbers_users nu
            JOIN clientes c ON c.id = nu.id_user
            WHERE CONCAT(c.codigo_pais, c.celular) = :phone
              AND nu.valid_until >= CURRENT_DATE
            ORDER BY nu.date_assigned DESC
        """.strip(),
        "sql_params": ["phone"],
        "static_text": None,
        "http_url": None, "http_method": None, "http_headers": None,
        "http_body_tpl": None, "http_timeout_seconds": None,
    },
    {
        "name": "consultar_estado_usuario",
        "description": (
            "Consulta el estado de la cuenta del usuario: si está activo/habilitado, "
            "si es VIP, y su nombre. "
            "Úsala cuando el usuario pregunta por su cuenta, estado, si está activo, etc."
        ),
        "tool_type": "SQL",
        "sql_dsn": PORTAL_DB_URL,
        "sql_query": """
            SELECT
                c.nombre,
                c.enabled AS cuenta_activa,
                c.vip,
                CASE WHEN s.activa IS TRUE AND s.fin > now() THEN true ELSE false END AS suscripcion_vigente
            FROM clientes c
            LEFT JOIN suscripciones s
                ON s.cliente_id = c.id AND s.activa = true AND s.fin > now()
            WHERE CONCAT(c.codigo_pais, c.celular) = :phone
            LIMIT 1
        """.strip(),
        "sql_params": ["phone"],
        "static_text": None,
        "http_url": None, "http_method": None, "http_headers": None,
        "http_body_tpl": None, "http_timeout_seconds": None,
    },
    {
        "name": "consultar_fin_suscripcion",
        "description": (
            "Consulta la fecha de vencimiento de la suscripción activa del usuario. "
            "Úsala cuando el usuario pregunta cuándo vence, hasta cuándo tiene acceso, "
            "cuándo expira su suscripción, etc."
        ),
        "tool_type": "SQL",
        "sql_dsn": PORTAL_DB_URL,
        "sql_query": """
            SELECT
                s.fin::date::text AS vence,
                s.activa
            FROM suscripciones s
            JOIN clientes c ON c.id = s.cliente_id
            WHERE CONCAT(c.codigo_pais, c.celular) = :phone
              AND s.activa = true
              AND s.fin > now()
            ORDER BY s.fin DESC
            LIMIT 1
        """.strip(),
        "sql_params": ["phone"],
        "static_text": None,
        "http_url": None, "http_method": None, "http_headers": None,
        "http_body_tpl": None, "http_timeout_seconds": None,
    },
    {
        "name": "consultar_saldo",
        "description": (
            "Consulta el saldo disponible del usuario en su cuenta. "
            "Úsala cuando el usuario pregunta por su saldo, cuánto tiene, cuánto dinero le queda, etc."
        ),
        "tool_type": "SQL",
        "sql_dsn": PORTAL_DB_URL,
        "sql_query": """
            SELECT saldo::text
            FROM clientes
            WHERE CONCAT(codigo_pais, celular) = :phone
            LIMIT 1
        """.strip(),
        "sql_params": ["phone"],
        "static_text": None,
        "http_url": None, "http_method": None, "http_headers": None,
        "http_body_tpl": None, "http_timeout_seconds": None,
    },
]


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        row = await conn.execute(
            text("SELECT id FROM public.tenants WHERE slug = :slug"),
            {"slug": TENANT_SLUG},
        )
        tenant = row.fetchone()
        if not tenant:
            print(f"ERROR: No se encontró el tenant con slug '{TENANT_SLUG}'")
            return
        tenant_id = tenant[0]
        print(f"Tenant encontrado: {tenant_id}")

        for tool in TOOLS:
            # Verificar si ya existe
            existing = await conn.execute(
                text(
                    "SELECT id FROM public.agent_tools "
                    "WHERE tenant_id = :tid AND name = :name"
                ),
                {"tid": tenant_id, "name": tool["name"]},
            )
            if existing.fetchone():
                print(f"  [SKIP] '{tool['name']}' ya existe")
                continue

            # asyncpg no convierte :name:: correctamente — embebemos los valores
            # literales seguros (enum fijo) y JSON (lista controlada) directamente.
            tool_type_lit = tool["tool_type"]          # 'HTTP' | 'SQL' | 'STATIC'
            sql_params_lit = json.dumps(tool["sql_params"])  # e.g. '["phone"]'

            await conn.execute(
                text(f"""
                    INSERT INTO public.agent_tools (
                        id, tenant_id, name, description, tool_type, enabled,
                        sql_dsn, sql_query, sql_params,
                        http_url, http_method, http_headers, http_body_tpl, http_timeout_seconds,
                        static_text,
                        created_at, updated_at
                    ) VALUES (
                        gen_random_uuid(), :tenant_id, :name, :description,
                        '{tool_type_lit}'::tool_type, true,
                        :sql_dsn, :sql_query, '{sql_params_lit}'::jsonb,
                        :http_url, :http_method, :http_headers, :http_body_tpl, :http_timeout_seconds,
                        :static_text,
                        now(), now()
                    )
                """),
                {
                    "tenant_id": tenant_id,
                    "name": tool["name"],
                    "description": tool["description"],
                    "sql_dsn": tool["sql_dsn"],
                    "sql_query": tool["sql_query"],
                    "http_url": tool["http_url"],
                    "http_method": tool["http_method"],
                    "http_headers": tool["http_headers"],
                    "http_body_tpl": tool["http_body_tpl"],
                    "http_timeout_seconds": tool["http_timeout_seconds"],
                    "static_text": tool["static_text"],
                },
            )
            print(f"  [OK]   '{tool['name']}' creada")

    await engine.dispose()
    print("Listo.")


if __name__ == "__main__":
    asyncio.run(main())
