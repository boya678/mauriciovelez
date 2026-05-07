"""
Actualiza el sql_dsn de las tools SQL del tenant mauriciovelez
para apuntar explícitamente al DB correcto (portal).

Ejecutar dentro del pod:
    kubectl exec -n mauriciovelez deploy/chatsystem-backend -- \
        python /app/update_tools_dsn.py

O localmente con acceso al chat DB:
    DATABASE_URL=<chat_dsn> python update_tools_dsn.py
"""
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# DSN del chat DB (donde viven los agent_tools)
CHAT_DB_URL = os.environ["DATABASE_URL"]

# DSN explícito que deben usar las tools para consultar datos del tenant
PORTAL_DB_URL = "postgresql+asyncpg://postgres:Ardilla1*@transferiadb.postgres.database.azure.com:5432/portal"

TENANT_SLUG = "mauriciovelez"

TOOL_NAMES = [
    "consultar_numeros_asignados",
    "consultar_estado_usuario",
    "consultar_fin_suscripcion",
    "consultar_saldo",
]


async def main() -> None:
    engine = create_async_engine(CHAT_DB_URL, echo=False)
    async with engine.begin() as conn:
        for name in TOOL_NAMES:
            result = await conn.execute(
                text(
                    "UPDATE agent_tools "
                    "SET sql_dsn = :dsn "
                    "FROM tenants t "
                    "WHERE agent_tools.tenant_id = t.id "
                    "  AND t.slug = :slug "
                    "  AND agent_tools.name = :name "
                    "RETURNING agent_tools.id, agent_tools.name"
                ),
                {"dsn": PORTAL_DB_URL, "slug": TENANT_SLUG, "name": name},
            )
            row = result.fetchone()
            if row:
                print(f"  ✔  {row.name}  →  dsn actualizado")
            else:
                print(f"  ✗  {name}  →  no encontrada (verifica slug y nombre)")

    await engine.dispose()
    print("Listo.")


asyncio.run(main())
