# Tabla `contactos`

Existe en cada schema de tenant (`t_{slug}.contactos`).

## Estructura

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | `VARCHAR(30)` PK | Número de teléfono del usuario (ej: `573001234567`) |
| `tags` | `TEXT` NOT NULL DEFAULT `''` | Etiquetas en formato `clave:valor` separadas por coma (ej: `plan:vip,ciudad:medellin`) |
| `created_at` | `TIMESTAMPTZ` | Fecha de primer contacto |

## Comportamiento

- Se crea un registro automáticamente cuando llega el primer mensaje de un número nuevo (worker `message_ingestion`).
- Si el número ya existe, no se modifica (`ON CONFLICT DO NOTHING`).
- Los tags se crean vacíos (`''`) y se editan manualmente directamente en la base de datos.
- La migración `0014` creó la tabla en todos los schemas existentes y sembró todos los números que ya tenían conversaciones.

## Relación

- Se hace `LEFT JOIN` con `conversations` en el endpoint `GET /api/v1/conversations` para retornar el campo `tags` junto a cada conversación.
- El frontend muestra los tags debajo del número en las 4 pestañas de la bandeja (lectura solamente).
