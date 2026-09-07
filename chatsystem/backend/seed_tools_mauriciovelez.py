"""
Seed script: crea o actualiza las herramientas SQL para el tenant mauriciovelez.

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

# Prefer the deployment secret. Existing installations can reuse the DSN from
# the original numbers tool when the variable has not been configured yet.
PORTAL_DB_URL = os.environ.get("PORTAL_DB_URL")

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
    {
        "name": "consultar_resumen_cliente",
        "description": (
            "Consulta un resumen actualizado del cliente: nombre, estado de cuenta, "
            "VIP, saldo y vigencia de su suscripción. Úsala para consultas generales "
            "sobre la cuenta; no muestra correo ni documento."
        ),
        "tool_type": "SQL",
        "sql_dsn": PORTAL_DB_URL,
        "sql_query": """
            SELECT
                c.nombre,
                c.enabled AS cuenta_activa,
                c.vip,
                c.saldo::text AS saldo,
                COALESCE(tc.nombre, 'Sin clasificación') AS tipo_cliente,
                (s.fin > now()) AS suscripcion_vigente,
                s.inicio::date::text AS inicio_suscripcion,
                s.fin::date::text AS fin_suscripcion
            FROM clientes c
            LEFT JOIN tipos_cliente tc ON tc.id = c.tipo_cliente
            LEFT JOIN LATERAL (
                SELECT inicio, fin
                FROM suscripciones
                WHERE cliente_id = c.id AND activa = true
                ORDER BY fin DESC
                LIMIT 1
            ) s ON true
            WHERE CONCAT(c.codigo_pais, c.celular) = :phone
            LIMIT 1
        """.strip(),
        "sql_params": ["phone"],
        "static_text": None,
        "http_url": None, "http_method": None, "http_headers": None,
        "http_body_tpl": None, "http_timeout_seconds": None,
    },
    {
        "name": "consultar_historial_suscripciones",
        "description": (
            "Consulta las últimas suscripciones del cliente con fechas de inicio, "
            "fin y estado. Úsala para revisar renovaciones anteriores o aclarar "
            "el historial de vigencias."
        ),
        "tool_type": "SQL",
        "sql_dsn": PORTAL_DB_URL,
        "sql_query": """
            SELECT
                s.inicio::date::text AS inicio,
                s.fin::date::text AS fin,
                s.activa,
                CASE
                    WHEN s.activa AND s.fin > now() THEN 'vigente'
                    WHEN s.fin <= now() THEN 'vencida'
                    ELSE 'inactiva'
                END AS estado
            FROM suscripciones s
            JOIN clientes c ON c.id = s.cliente_id
            WHERE CONCAT(c.codigo_pais, c.celular) = :phone
            ORDER BY s.inicio DESC
            LIMIT 10
        """.strip(),
        "sql_params": ["phone"],
        "static_text": None,
        "http_url": None, "http_method": None, "http_headers": None,
        "http_body_tpl": None, "http_timeout_seconds": None,
    },
    {
        "name": "consultar_comprobantes_vip",
        "description": (
            "Consulta los últimos comprobantes VIP registrados para el teléfono del "
            "cliente: fecha, monto, número y descripción. Un registro indica recepción "
            "del comprobante, no aprobación ni activación del pago."
        ),
        "tool_type": "SQL",
        "sql_dsn": PORTAL_DB_URL,
        "sql_query": """
            SELECT
                cv.created_at::date::text AS fecha,
                cv.monto::text AS monto,
                cv.comprobante_num,
                cv.descripcion
            FROM comprobantes_vip cv
            WHERE regexp_replace(cv.celular, '[^0-9]', '', 'g') =
                  right(regexp_replace(:phone, '[^0-9]', '', 'g'), 10)
            ORDER BY cv.created_at DESC
            LIMIT 10
        """.strip(),
        "sql_params": ["phone"],
        "static_text": None,
        "http_url": None, "http_method": None, "http_headers": None,
        "http_body_tpl": None, "http_timeout_seconds": None,
    },
    {
        "name": "consultar_boletas_rifa",
        "description": (
            "Consulta las boletas de rifas asignadas al cliente, mostrando rifa, número, "
            "fecha de asignación y estado. Úsala cuando pregunte por sus boletas o números "
            "de una rifa."
        ),
        "tool_type": "SQL",
        "sql_dsn": PORTAL_DB_URL,
        "sql_query": """
            SELECT
                r.titulo AS rifa,
                rb.numero AS boleta,
                rb.asignado_en::date::text AS fecha_asignacion,
                r.fecha_inicio::text,
                r.fecha_fin::text,
                r.estado
            FROM rifa_boletas rb
            JOIN rifas r ON r.id = rb.rifa_id
            JOIN clientes c ON c.id = rb.cliente_id
            WHERE CONCAT(c.codigo_pais, c.celular) = :phone
            ORDER BY rb.asignado_en DESC, rb.numero
            LIMIT 30
        """.strip(),
        "sql_params": ["phone"],
        "static_text": None,
        "http_url": None, "http_method": None, "http_headers": None,
        "http_body_tpl": None, "http_timeout_seconds": None,
    },
    {
        "name": "consultar_rifas_activas",
        "description": (
            "Consulta las rifas activas disponibles: título, descripción, fechas, "
            "requisitos VIP y boletas otorgadas por renovación. No requiere identificar "
            "al cliente."
        ),
        "tool_type": "SQL",
        "sql_dsn": PORTAL_DB_URL,
        "sql_query": """
            SELECT
                titulo,
                descripcion,
                fecha_inicio::text,
                fecha_fin::text,
                boletas_por_renovacion,
                solo_vip,
                estado
            FROM rifas
            WHERE estado = 'activa'
              AND fecha_fin >= CURRENT_DATE
            ORDER BY fecha_inicio DESC
            LIMIT 10
        """.strip(),
        "sql_params": [],
        "static_text": None,
        "http_url": None, "http_method": None, "http_headers": None,
        "http_body_tpl": None, "http_timeout_seconds": None,
    },
    {
        "name": "consultar_historial_numeros",
        "description": (
            "Consulta los últimos números históricos asignados al cliente con fecha y tipo. "
            "Úsala cuando pregunte por números anteriores, no para reemplazar la consulta "
            "de números vigentes."
        ),
        "tool_type": "SQL",
        "sql_dsn": PORTAL_DB_URL,
        "sql_query": """
            SELECT
                nh.number,
                nh.type,
                nh.date::text AS fecha
            FROM numbers_historic nh
            JOIN clientes c ON c.id = nh.id_user
            WHERE CONCAT(c.codigo_pais, c.celular) = :phone
            ORDER BY nh.date DESC, nh.id DESC
            LIMIT 20
        """.strip(),
        "sql_params": ["phone"],
        "static_text": None,
        "http_url": None, "http_method": None, "http_headers": None,
        "http_body_tpl": None, "http_timeout_seconds": None,
    },
    {
        "name": "consultar_aciertos",
        "description": (
            "Consulta aciertos históricos de los números del cliente: número, tipo, "
            "lotería, fecha y resultado. Úsala cuando pregunte si alguno de sus números "
            "tuvo aciertos."
        ),
        "tool_type": "SQL",
        "sql_dsn": PORTAL_DB_URL,
        "sql_query": """
            SELECT
                nh.number,
                nh.type AS tipo_numero,
                na.tipo AS tipo_acierto,
                lr.fecha::text,
                lr.loteria,
                lr.resultado,
                lr.serie
            FROM numero_aciertos na
            JOIN numbers_historic nh ON nh.id = na.historic_id
            JOIN loteria_resultados lr ON lr.id = na.resultado_id
            JOIN clientes c ON c.id = nh.id_user
            WHERE CONCAT(c.codigo_pais, c.celular) = :phone
            ORDER BY lr.fecha DESC, na.created_at DESC
            LIMIT 30
        """.strip(),
        "sql_params": ["phone"],
        "static_text": None,
        "http_url": None, "http_method": None, "http_headers": None,
        "http_body_tpl": None, "http_timeout_seconds": None,
    },
    {
        "name": "consultar_resultado_loteria",
        "description": (
            "Consulta los resultados más recientes de una lotería indicada por el usuario. "
            "Solicita el nombre de la lotería si no está claro."
        ),
        "tool_type": "SQL",
        "sql_dsn": PORTAL_DB_URL,
        "sql_query": """
            SELECT
                fecha::text,
                loteria,
                resultado,
                serie
            FROM loteria_resultados
            WHERE lower(loteria) LIKE '%' || lower(:loteria) || '%'
               OR lower(slug) LIKE '%' || lower(:loteria) || '%'
            ORDER BY fecha DESC
            LIMIT 10
        """.strip(),
        "sql_params": ["loteria"],
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

        portal_db_url = PORTAL_DB_URL
        if not portal_db_url:
            result = await conn.execute(
                text(
                    "SELECT sql_dsn FROM public.agent_tools "
                    "WHERE tenant_id = :tid "
                    "AND name = 'consultar_numeros_asignados' "
                    "AND sql_dsn IS NOT NULL LIMIT 1"
                ),
                {"tid": tenant_id},
            )
            portal_db_url = result.scalar_one_or_none()
        if not portal_db_url:
            raise RuntimeError(
                "Configura PORTAL_DB_URL o crea primero consultar_numeros_asignados."
            )

        for definition in TOOLS:
            tool = {**definition, "sql_dsn": portal_db_url}
            tool_type_lit = tool["tool_type"]
            sql_params_lit = json.dumps(tool["sql_params"])

            existing = await conn.execute(
                text(
                    "SELECT id FROM public.agent_tools "
                    "WHERE tenant_id = :tid AND name = :name"
                ),
                {"tid": tenant_id, "name": tool["name"]},
            )
            if existing.fetchone():
                await conn.execute(
                    text(f"""
                        UPDATE public.agent_tools SET
                            description = :description,
                            tool_type = '{tool_type_lit}'::tool_type,
                            enabled = true,
                            sql_dsn = :sql_dsn,
                            sql_query = :sql_query,
                            sql_params = '{sql_params_lit}'::jsonb,
                            http_url = :http_url,
                            http_method = :http_method,
                            http_headers = :http_headers,
                            http_body_tpl = :http_body_tpl,
                            http_timeout_seconds = :http_timeout_seconds,
                            static_text = :static_text,
                            updated_at = now()
                        WHERE tenant_id = :tenant_id AND name = :name
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
                print(f"  [OK]   '{tool['name']}' actualizada")
                continue

            # asyncpg no convierte :name:: correctamente — embebemos los valores
            # literales seguros (enum fijo) y JSON (lista controlada) directamente.
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
