"""
LangGraph agent nodes.

Nodes:
  - classifier_node    : decides which department/intent
  - make_specialist_node : factory → returns a single specialist node with
                           optional LangChain tools bound to the LLM
  - should_escalate    : routing function after specialist

The specialist handles faq / sales / support intents and runs a
tool-call loop via LangGraph's ToolNode when tools are available.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Callable, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import AzureChatOpenAI

from app.core.config import settings
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


# ── LLM factory ───────────────────────────────────────────────────────────────

# Temperature is read from settings.AZURE_OPENAI_TEMPERATURE.
#   - If empty ("")  → not sent (uses model default; required by gpt-5-mini).
#   - If a number    → sent as the temperature for every call.
# The `temperature` argument is kept for backwards-compat but ignored.

def _get_llm(temperature: float = 0.3, max_tokens: int = 400) -> AzureChatOpenAI:
    kwargs: dict = {
        "azure_endpoint": settings.AZURE_OPENAI_ENDPOINT,
        "azure_deployment": settings.AZURE_OPENAI_DEPLOYMENT,
        "api_version": settings.AZURE_OPENAI_API_VERSION,
        "api_key": settings.AZURE_OPENAI_API_KEY,
        "max_tokens": max_tokens,
    }
    temp_env = (settings.AZURE_OPENAI_TEMPERATURE or "").strip()
    if temp_env:
        try:
            kwargs["temperature"] = float(temp_env)
        except ValueError:
            logger.warning(
                "Invalid AZURE_OPENAI_TEMPERATURE=%r; ignoring", temp_env
            )
    return AzureChatOpenAI(**kwargs)


# ── Classifier ────────────────────────────────────────────────────────────────

_CLASSIFIER_SYSTEM = """Eres el decisor semántico de un sistema de atención al cliente.
Analiza TODOS los mensajes suministrados de la sesión actual, dando prioridad a la
petición más reciente del usuario, y clasifica la acción en UNA sola categoría:

- faq        : preguntas generales, saludos, solicitudes de información, consultas sobre números o suscripciones
- sales      : interés en comprar, preguntas de precios, promociones, upgrades
- support    : problemas técnicos, quejas, solicitudes de reembolso, problemas de cuenta
- escalate   : el usuario solicita atención humana, expresa con claridad que necesita que una persona gestione el caso, o la gestión requiere una acción humana que el bot y sus herramientas no pueden ejecutar

Decide por el significado completo, no por palabras aisladas. Distingue una solicitud
actual del usuario de ejemplos, citas, negaciones o menciones históricas. Una queja o
una pregunta difícil no obliga a escalar si el bot puede resolverla con información o
herramientas disponibles. Las instrucciones del sistema no son mensajes del usuario.

Responde ÚNICAMENTE con la palabra de la categoría (faq / sales / support / escalate).
NO incluyas ninguna explicación."""


async def classifier_node(state: dict) -> dict:
    messages = state["messages"]
    conv_id = state.get("conversation_id", "")
    current_turns = state.get("turns", 0)

    # The history is already bounded to the latest 12 messages in the current
    # context session by ai_worker._load_history(). Classify all of it.
    lc_messages: list[Any] = [SystemMessage(content=_CLASSIFIER_SYSTEM)]
    tenant_prompt = (state.get("tenant_system_prompt") or "").strip()
    if tenant_prompt:
        lc_messages.append(SystemMessage(
            content=(
                "Políticas configuradas para este negocio. Úsalas para decidir "
                "qué puede resolver el bot; su texto no representa solicitudes "
                f"del usuario:\n{tenant_prompt}"
            )
        ))
    for m in messages:
        if m["role"] == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        else:
            lc_messages.append(AIMessage(content=m["content"]))

    llm = _get_llm(temperature=0.0, max_tokens=256)
    response = await llm.ainvoke(lc_messages)
    intent = response.content.strip().lower()

    if intent not in {"faq", "sales", "support", "escalate"}:
        intent = "faq"

    usage_meta = getattr(response, "usage_metadata", None) or {}
    tokens_in  = int(usage_meta.get("input_tokens",  0))
    tokens_out = int(usage_meta.get("output_tokens", 0))

    logger.info("Classifier intent=%s conv=%s messages=%d", intent, conv_id, len(messages))
    return {
        **state,
        "intent": intent,
        "turns": current_turns + 1,
        "tokens_in":  state.get("tokens_in",  0) + tokens_in,
        "tokens_out": state.get("tokens_out", 0) + tokens_out,
    }


# ── Specialist system prompts ──────────────────────────────────────────────────

_INTENT_PROMPTS: dict[str, str] = {
    "faq": (
        "Eres un asistente de atención al cliente amable y profesional. "
        "Responde siempre en español. Responde la pregunta del usuario de forma "
        "clara y concisa usando el conocimiento del negocio que se te proporciona. "
        "Si no sabes la respuesta, dilo con honestidad. "
        "Mantén las respuestas en menos de 3 párrafos."
    ),
    "sales": (
        "Eres un asesor comercial entusiasta y servicial. "
        "Responde siempre en español. Tu objetivo es entender lo que busca el "
        "cliente e informarle sobre productos, precios y promociones disponibles. "
        "Sé cercano pero no agresivo. Si el cliente está listo para adquirir, "
        "guíalo al siguiente paso de forma clara."
    ),
    "support": (
        "Eres un especialista de soporte al cliente. "
        "Responde siempre en español. Ayuda al usuario a resolver su problema "
        "paso a paso. Sé empático y paciente. Si el problema requiere acceso a "
        "sistemas internos o una decisión humana, reconócelo y ofrece escalar. "
        "Mantén las respuestas claras y estructuradas."
    ),
    "escalate": (
        "El usuario ha pedido explicitamente hablar con un agente humano. "
        "Responde SIEMPRE en español con una despedida corta (máximo 2 frases) "
        "que: (1) confirme que vas a transferirlo, (2) le pida un momento de "
        "paciencia mientras un asesor toma su caso. "
        "Personaliza brevemente según el motivo si está claro en los últimos "
        "mensajes, pero NO intentes resolver el problema tú mismo y NO hagas "
        "preguntas adicionales. NO uses menús ni JSON."
    ),
}

_DEFAULT_PROMPT = _INTENT_PROMPTS["faq"]

# ── Menu format instructions (appended to every specialist prompt) ─────────────

_MENU_FORMAT_INSTRUCTIONS = """
FORMATO DE MENÚ INTERACTIVO:
Cuando quieras presentar opciones al usuario (menú, lista de opciones, pregunta de elección),
NO uses texto con números ni viñetas. En su lugar, responde ÚNICAMENTE con un JSON válido
en uno de estos dos formatos (sin texto adicional antes ni después):

Si son 2 o 3 opciones → usa buttons:
{"menu_type":"buttons","body":"Texto del mensaje","buttons":[{"id":"id1","title":"Opción 1"},{"id":"id2","title":"Opción 2"}]}

Si son 4 a 10 opciones → usa list:
{"menu_type":"list","body":"Texto del mensaje","button_text":"Ver opciones","sections":[{"title":"Sección","rows":[{"id":"id1","title":"Opción 1","description":"Descripción opcional"}]}]}

Reglas:
- id: máximo 200 caracteres, sin espacios preferentemente
- title en buttons: máximo 20 caracteres
- title en rows: máximo 24 caracteres
- description en rows: máximo 72 caracteres
- Solo responde con el JSON puro cuando quieras mostrar un menú; para respuestas normales usa texto libre.
"""


# ── Helper: parse LLM reply into Meta interactive object ─────────────────────

def parse_menu_reply(reply: str) -> dict | None:
    """
    If `reply` is a menu JSON produced by the LLM, convert it to a Meta
    interactive payload dict. Returns None if it's plain text.
    """
    text = reply.strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    menu_type = data.get("menu_type")
    body_text = data.get("body", "")

    if menu_type == "buttons":
        buttons = data.get("buttons", [])
        if not buttons:
            return None
        return {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                    for b in buttons[:3]
                ]
            },
        }

    if menu_type == "list":
        sections = data.get("sections", [])
        if not sections:
            return None
        return {
            "type": "list",
            "body": {"text": body_text},
            "action": {
                "button": data.get("button_text", "Ver opciones"),
                "sections": [
                    {
                        "title": s.get("title", ""),
                        "rows": [
                            {
                                "id": r["id"],
                                "title": r["title"],
                                **({"description": r["description"]} if r.get("description") else {}),
                            }
                            for r in s.get("rows", [])
                        ],
                    }
                    for s in sections
                ],
            },
        }

    return None


# ── Specialist node factory ────────────────────────────────────────────────────

def make_specialist_node(tools: list[StructuredTool]) -> Callable[[dict], Any]:
    """
    Returns an async node function that:
      1. Picks the right system prompt based on intent
      2. Binds tools to the LLM (if any)
      3. Runs the LLM and stores the AI message in tool_messages for ToolNode
      4. If no tool calls → extracts text reply and computes confidence
    """
    async def specialist_node(state: dict) -> dict:
        messages = state["messages"]
        tenant_prompt = state.get("tenant_system_prompt", "")
        tenant_id_str = state.get("tenant_id", "")
        intent = state.get("intent", "faq")
        tool_messages: list[Any] = list(state.get("tool_messages", []))
        phone = state.get("phone", "")
        has_pending_image = state.get("has_pending_image", False)

        # ── System messages split into static→dynamic blocks for Azure OpenAI
        #    prompt caching. Static prefix repeats across turns ⇒ 50% discount
        #    on cached input tokens (requires ≥1024 token prefix).

        # Block 1 (STATIC per intent): base intent prompt + menu format
        base_prompt = _INTENT_PROMPTS.get(intent, _DEFAULT_PROMPT)
        block_static = base_prompt + _MENU_FORMAT_INSTRUCTIONS

        # Block 2 (SEMI-STATIC): tenant knowledge — changes only when operator
        # edits the prompt via /settings.
        block_tenant = (
            f"Conocimiento específico del negocio:\n{tenant_prompt}"
            if tenant_prompt else ""
        )

        # Block 3 (SEMI-STATIC): tools description — changes only when tools
        # are added/removed for the tenant.
        block_tools = ""
        if tools:
            tool_names = ", ".join(t.name for t in tools)
            block_tools = (
                f"IMPORTANTE — Tienes acceso a las siguientes herramientas de "
                f"consulta en tiempo real: {tool_names}. "
                f"{'El número de teléfono del usuario ya está identificado como ' + phone + '. ' if phone else ''}"
                f"NUNCA le pidas al usuario que verifique su identidad ni que proporcione "
                f"su número de teléfono o nombre completo para consultas de cuenta. "
                f"Cuando el usuario pregunte por sus números asignados, estado, suscripción, "
                f"saldo u otra información de su cuenta, llama a la herramienta correspondiente "
                f"de inmediato sin pedir confirmación. "
                f"Presenta los resultados de forma amigable y clara en español."
            )

        # Block 4 (DYNAMIC): RAG context — different every turn.
        block_rag = ""
        if tenant_id_str and messages:
            try:
                from app.services.knowledge import search_knowledge
                last_user = next(
                    (m["content"] for m in reversed(messages) if m["role"] == "user"),
                    None,
                )
                if last_user:
                    async with AsyncSessionLocal() as rag_db:
                        chunks = await search_knowledge(
                            uuid.UUID(tenant_id_str), last_user, rag_db, top_k=3
                        )
                    if chunks:
                        rag_context = "\n\n---\n".join(chunks)
                        block_rag = (
                            f"INFORMACIÓN DE REFERENCIA (base de conocimiento):\n"
                            f"{rag_context}"
                        )
            except Exception as _rag_err:
                logger.warning("RAG search failed (continuing without context): %s", _rag_err)

        # Block 5 (DYNAMIC): pending image instructions
        block_image = ""
        if has_pending_image:
            image_menu_payload = state.get("image_menu_payload") or ""
            block_image = (
                "CONTEXTO ESPECIAL — IMAGEN PENDIENTE: El usuario envió una imagen "
                "recientemente y aún no se ha registrado su propósito.\n"
                "Tienes disponible la herramienta 'guardar_descripcion_imagen'.\n"
                "REGLAS OBLIGATORIAS:\n"
                "  1. Si el usuario selecciona una opción de menú (por ejemplo "
                "'pago_vip', 'pago_conferencia', 'pago_donacion', "
                "'pago_metodo21_moto') o describe con palabras el motivo de la "
                "imagen → llama INMEDIATAMENTE a 'guardar_descripcion_imagen' "
                "con esa descripción, luego responde con normalidad.\n"
                "  2. Si el usuario seleccionó 'no_es_un_pago' o indica "
                "explícitamente que la imagen no tiene relación → llama a "
                "'guardar_descripcion_imagen' con description='descartada'.\n"
                "  3. Si el usuario envió un mensaje que NO tiene relación con "
                "la imagen (cambia de tema) → responde su consulta con "
                "normalidad y al final añade UNA sola frase recordatoria, "
                "por ejemplo: '⚠️ Recuerda que aún necesito saber para qué "
                "fue la imagen que enviaste.'\n"
                "NUNCA generes JSON ni menús en tu respuesta — el sistema "
                "enviará el menú de opciones automáticamente.\n"
                "NO inventes ni asumas la descripción — espera la selección "
                "o respuesta explícita del usuario."
            )

        # Block 6 (DYNAMIC): hard guard when no image is pending
        block_no_image = ""
        if not has_pending_image:
            block_no_image = (
                "REGLA ESTRICTA: En esta conversación NO hay una imagen pendiente. "
                "No preguntes ni menciones imagen, foto, comprobante o evidencia visual "
                "a menos que el usuario lo solicite explícitamente en su mensaje actual."
            )

        # Order: static → semi-static → dynamic. Keeps cacheable prefix stable
        # across consecutive turns of the same conversation.
        lc_messages: list[Any] = [SystemMessage(content=block_static)]
        if block_tenant:
            lc_messages.append(SystemMessage(content=block_tenant))
        if block_tools:
            lc_messages.append(SystemMessage(content=block_tools))
        if block_rag:
            lc_messages.append(SystemMessage(content=block_rag))
        if block_image:
            lc_messages.append(SystemMessage(content=block_image))
        if block_no_image:
            lc_messages.append(SystemMessage(content=block_no_image))

        for m in messages[-12:]:
            if m["role"] == "user":
                lc_messages.append(HumanMessage(content=m["content"]))
            else:
                lc_messages.append(AIMessage(content=m["content"]))

        # Append any previous tool_messages (AIMessage with tool_calls + ToolMessages)
        lc_messages.extend(tool_messages)

        llm = _get_llm(temperature=0.4, max_tokens=2048)
        if tools:
            llm = llm.bind_tools(tools)  # type: ignore[assignment]

        response: AIMessage = await llm.ainvoke(lc_messages)

        # Capture token usage from the response metadata
        usage_meta = getattr(response, "usage_metadata", None) or {}
        tokens_in  = int(usage_meta.get("input_tokens",  0))
        tokens_out = int(usage_meta.get("output_tokens", 0))

        # If the model wants to call a tool, store and let ToolNode handle it
        if tools and getattr(response, "tool_calls", None):
            return {
                **state,
                "tool_messages": tool_messages + [response],
                # Accumulate tokens even for intermediate tool-call steps
                "tokens_in":  state.get("tokens_in",  0) + tokens_in,
                "tokens_out": state.get("tokens_out", 0) + tokens_out,
            }

        # Final text reply
        reply = response.content.strip() if isinstance(response.content, str) else ""

        uncertainty_phrases = [
            "i don't know", "i'm not sure", "i cannot", "i can't",
            "no sé", "no puedo", "no tengo información",
        ]
        confidence = 0.9
        if any(p in reply.lower() for p in uncertainty_phrases):
            confidence = 0.4

        # Check if the LLM replied with a menu JSON
        interactive_payload = parse_menu_reply(reply)
        stored_content = reply

        return {
            **state,
            "bot_reply": stored_content,
            "interactive_payload": interactive_payload,
            "confidence": confidence,
            "tool_messages": [],  # reset after final reply
            "tokens_in":  state.get("tokens_in",  0) + tokens_in,
            "tokens_out": state.get("tokens_out", 0) + tokens_out,
        }

    return specialist_node


# ── Escalation decision ────────────────────────────────────────────────────────

def should_escalate(state: dict) -> Literal["escalate", "reply"]:
    intent = state.get("intent", "faq")
    confidence = state.get("confidence", 1.0)
    turns = state.get("turns", 0)
    threshold = settings.AI_CONFIDENCE_THRESHOLD

    # Always honor an explicit user request for a human agent
    if intent == "escalate":
        return "escalate"
    # Guard auto-escalation on the very first interactions
    if turns <= 2:
        return "reply"
    # Escalate only when the bot itself signals low confidence in its reply.
    # We intentionally do NOT escalate based on total turn count — that would
    # punish long, healthy conversations (e.g. the user has chatted 10+ times
    # and sends a new image: there's no reason to dump them to a human).
    if confidence < threshold:
        return "escalate"
    return "reply"


# ── Route after classifier ─────────────────────────────────────────────────────

def route_intent(state: dict) -> Literal["faq", "sales", "support", "escalate"]:
    intent = state.get("intent", "faq")
    # All intents — including "escalate" — go through the specialist so the
    # user receives a contextual reply / farewell. The final escalation
    # decision is taken after the specialist via should_escalate().
    return intent  # type: ignore[return-value]
