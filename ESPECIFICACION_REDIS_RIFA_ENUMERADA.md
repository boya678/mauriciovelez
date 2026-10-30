# Rifa enumerada: solicitud de boletas por Redis

## Objetivo

Cuando un cliente pulsa el botón **SOLICITAR BOLETAS** de la plantilla `rifa_automatica_aviso`, el chatsystem debe dejar un mensaje en Redis. El backend lo consume, asigna los números y le envía las boletas a ese celular.

## Redis

- Mismo Redis que ya se usa: `redis://redis:6379/0`.
- Lista: `rifa_enumerada:solicitudes`.
- Comando: `RPUSH rifa_enumerada:solicitudes '<json>'`.

## Contenido (un JSON por solicitud)

```json
{"celular": "573224920775", "contexto_wamid": "wamid.HBgM..."}
```

| Campo | Obligatorio | Descripción |
|---|---|---|
| `celular` | Sí | Número del cliente, solo dígitos, con 57 (el campo `from` del mensaje entrante). El backend usa los últimos 10 dígitos. |
| `contexto_wamid` | No (recomendado) | `context.id` del mensaje entrante, es decir, el id del aviso al que respondió. Con él la solicitud se asocia al aviso exacto. Si no está, se omite o va en `null`. |

## Cuándo se deja el mensaje

- Solo cuando el mensaje entrante sea la respuesta al botón: `type = "button"` y `button.text` igual a `SOLICITAR BOLETAS` (comparar sin distinguir mayúsculas y sin espacios al borde).
- Si el cliente escribe ese texto a mano en vez de pulsar el botón, también cuenta. En ese caso no habrá `contexto_wamid`.
- Ningún otro mensaje debe generar una entrada en la lista.

## Lo que el chatsystem NO debe hacer

- No filtrar duplicados ni verificar si el cliente ya recibió las boletas. El backend ignora las pulsaciones repetidas y los celulares sin aviso.
- No enviar nada al cliente: el backend responde por su cuenta.
- No usar otra lista ni otro formato: el backend solo lee `rifa_enumerada:solicitudes`.

## Qué hace el backend

1. Lee la lista con `BLPOP`.
2. Busca el aviso enviado: primero por `contexto_wamid`; si no hay, el último aviso enviado a ese celular que aún no haya sido solicitado.
3. Si lo encuentra y no estaba solicitado, asigna las boletas (la cantidad configurada al enviar el lote), las registra y las envía como mensajes de imagen, separados unos 6,5 segundos entre sí.
4. Si no hay aviso para ese celular, o ya fue solicitado, ignora el mensaje y lo deja en el log.
5. Si falla al procesar, mueve el mensaje a `rifa_enumerada:solicitudes:dead` con el motivo y la hora.

## Prueba rápida

Requiere un lote ya enviado con el aviso a ese número.

```
redis-cli -h redis -n 0 RPUSH rifa_enumerada:solicitudes '{"celular":"573224920775"}'
```

Para ver mensajes con error:

```
redis-cli -h redis -n 0 LRANGE rifa_enumerada:solicitudes:dead 0 -1
```

## Nota para quien implemente

El formato del JSON no cambia. Si el parser del chatsystem guarda el texto del botón o el id de contexto en otros campos, solo hay que adaptar de dónde se toman `celular` y `contexto_wamid`.
