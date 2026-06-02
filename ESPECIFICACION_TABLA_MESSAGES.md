# Especificación Tabla `messages`

## Contexto
La tabla `messages` es multi-tenant y vive dentro de cada esquema de tenant (`t_<slug>`), por ejemplo `t_mauriciovelez.messages`.

Se crea en el aprovisionamiento de tenant y luego se extiende vía migraciones.

## Definición funcional
Almacena cada mensaje de una conversación (usuario, bot o agente humano), incluyendo texto y metadatos de estado/procesamiento.

## Estructura de columnas

| Columna | Tipo | Nulo | Default | Descripción |
|---|---|---|---|---|
| `id` | `UUID` | No | — | PK del mensaje. |
| `conversation_id` | `UUID` | No | — | FK a `conversations(id)` del mismo esquema tenant. |
| `external_id` | `VARCHAR(128)` / `VARCHAR(200)` | Sí | `NULL` | ID externo (ej. WhatsApp `wamid`). Único cuando existe. |
| `sender_type` | `VARCHAR(20)` | No | — | Origen del mensaje: `user`, `bot`, `human`. |
| `content` | `TEXT` | No | — | Contenido principal del mensaje (texto mostrado en chat). |
| `message_type` | `VARCHAR(30)` | No | `'text'` | Tipo lógico del mensaje (`text`, `image`, etc.). |
| `status` | `VARCHAR(20)` | No | `'pending'` | Estado de pipeline: `pending`, `processing`, `processed`, `error`. |
| `created_at` | `TIMESTAMPTZ` | No | `NOW()` | Fecha de creación del registro. |
| `media_content` | `TEXT` | Sí | `NULL` | Contenido multimedia en base64 (migración 0004). |
| `media_mime_type` | `VARCHAR(100)` | Sí | `NULL` | MIME type del multimedia (migración 0004). |
| `imagen_descripcion` | `TEXT` | Sí | `NULL` | Descripción textual de imagen (migración 0005). |

## Claves y restricciones

- Clave primaria: `id`.
- Clave foránea: `conversation_id -> conversations(id)` dentro del mismo esquema tenant.
- Restricción única: `external_id` (`UNIQUE`).

## Índices

- Índice por conversación:
  - `idx_msg_conv` (DDL de aprovisionamiento)
  - También aparece `ix_msg_conversation`/`ix_msg_conv` desde ORM según instalación.
- Índice/constraint única para `external_id`:
  - `UNIQUE` a nivel columna y/o constraint nominal (`uq_msg_external_id`) según evolución del esquema.

## Enums usados por la aplicación

### `SenderType`
- `user`
- `bot`
- `human`

### `MessageStatus`
- `pending`
- `processing`
- `processed`
- `error`

## Notas de evolución del esquema

1. Base inicial (aprovisionamiento tenant): columnas principales de mensajes.
2. Migración `0004`: agrega `media_content`, `media_mime_type` en todos los esquemas `t_%`.
3. Migración `0005`: agrega `imagen_descripcion` en todos los esquemas `t_%`.

## Observaciones importantes

- Hay variación histórica en `external_id` (`VARCHAR(128)` en DDL inicial de tenant vs `VARCHAR(200)` en modelo ORM). En operación normal no afecta mientras el valor no exceda el límite físico de la tabla existente.
- La tabla es por tenant (no global), por lo que toda consulta debe ejecutarse en el esquema correcto del tenant.

## Uso típico en pipeline

1. Se inserta mensaje entrante/saliente con `status='pending'`.
2. Workers lo llevan a `processing`.
3. Al finalizar envío/procesamiento: `processed` o `error`.
