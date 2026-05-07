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
from typing import Any, Callable, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import AzureChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── LLM factory ───────────────────────────────────────────────────────────────

def _get_llm(temperature: float = 0.3) -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        azure_deployment=settings.AZURE_OPENAI_DEPLOYMENT,
        api_version=settings.AZURE_OPENAI_API_VERSION,
        api_key=settings.AZURE_OPENAI_API_KEY,
        temperature=temperature,
        max_tokens=800,
    )


# ── Classifier ────────────────────────────────────────────────────────────────

_CLASSIFIER_SYSTEM = """Eres un clasificador de intenciones para un sistema de atención al cliente.
Analiza el historial de conversación y clasifica la intención del usuario en UNA sola categoría:

- faq        : preguntas generales, saludos, solicitudes de información, consultas sobre números o suscripciones
- sales      : interés en comprar, preguntas de precios, promociones, upgrades
- support    : problemas técnicos, quejas, solicitudes de reembolso, problemas de cuenta
- escalate   : el usuario EXPLÍCITAMENTE pide hablar con una persona humana o un agente, o está extremadamente enojado con insultos

REGLA IMPORTANTE: Usa "escalate" ÚNICAMENTE cuando el usuario pida un agente humano de forma explícita
(frases como "quiero hablar con una persona", "pásame con un asesor", "necesito un humano").
Una queja, una pregunta difícil o un tono molesto NO es motivo para clasificar como "escalate".

Responde ÚNICAMENTE con la palabra de la categoría (faq / sales / support / escalate).
NO incluyas ninguna explicación."""


async def classifier_node(state: dict) -> dict:
    messages = state["messages"]
    system_prompt = state.get("tenant_system_prompt", "")

    lc_messages = [SystemMessage(content=_CLASSIFIER_SYSTEM)]
    if system_prompt:
        lc_messages.append(SystemMessage(content=f"Business context:\n{system_prompt}"))
    for m in messages[-8:]:
        if m["role"] == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        else:
            lc_messages.append(AIMessage(content=m["content"]))

    llm = _get_llm(temperature=0.0)
    response = await llm.ainvoke(lc_messages)
    intent = response.content.strip().lower()

    if intent not in {"faq", "sales", "support", "escalate"}:
        intent = "faq"

    logger.debug("Classifier intent: %s", intent)
    return {**state, "intent": intent, "turns": state.get("turns", 0) + 1}


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
        intent = state.get("intent", "faq")
        tool_messages: list[Any] = list(state.get("tool_messages", []))

        base_prompt = _INTENT_PROMPTS.get(intent, _DEFAULT_PROMPT)
        system_content = base_prompt + _MENU_FORMAT_INSTRUCTIONS
        if tenant_prompt:
            system_content += f"\n\nConocimiento específico del negocio:\n{tenant_prompt}"

        # When waiting for the user to describe a previously sent image, instruct
        # the LLM to embed a special tag if the user's message answers that question.
        has_pending_image = state.get("has_pending_image", False)
        if has_pending_image:
            system_content += (
                "\n\nCONTEXTO ESPECIAL — IMAGEN PENDIENTE: El usuario envió una imagen "
                "recientemente y aún no ha explicado para qué es. "
                "Si el último mensaje del usuario responde claramente esa pregunta "
                "(describe el motivo, tipo, o propósito de la imagen), incluye al "
                "INICIO de tu respuesta la etiqueta [IMG_CTX:descripción breve]. "
                "Ejemplo: [IMG_CTX:pago conferencia marzo]. "
                "Si el mensaje NO tiene relación con la imagen, responde su consulta "
                "con normalidad y AL FINAL recuérdale amablemente que aún necesitas "
                "saber para qué fue la imagen que envió (una sola frase, de forma natural)."
            )

        # If tools are available, tell the LLM how to use them and that the
        # user's phone is already identified — never ask for identity verification.
        phone = state.get("phone", "")
        if tools:
            tool_names = ", ".join(t.name for t in tools)
            system_content += (
                f"\n\nIMPORTANTE — Tienes acceso a las siguientes herramientas de "
                f"consulta en tiempo real: {tool_names}. "
                f"{'El número de teléfono del usuario ya está identificado como ' + phone + '. ' if phone else ''}"
                f"NUNCA le pidas al usuario que verifique su identidad ni que proporcione "
                f"su número de teléfono o nombre completo para consultas de cuenta. "
                f"Cuando el usuario pregunte por sus números asignados, estado, suscripción, "
                f"saldo u otra información de su cuenta, llama a la herramienta correspondiente "
                f"de inmediato sin pedir confirmación. "
                f"Presenta los resultados de forma amigable y clara en español."
            )

        lc_messages: list[Any] = [SystemMessage(content=system_content)]
        for m in messages[-12:]:
            if m["role"] == "user":
                lc_messages.append(HumanMessage(content=m["content"]))
            else:
                lc_messages.append(AIMessage(content=m["content"]))

        # Append any previous tool_messages (AIMessage with tool_calls + ToolMessages)
        lc_messages.extend(tool_messages)

        llm = _get_llm(temperature=0.4)
        if tools:
            llm = llm.bind_tools(tools)  # type: ignore[assignment]

        response: AIMessage = await llm.ainvoke(lc_messages)

        # If the model wants to call a tool, store and let ToolNode handle it
        if tools and getattr(response, "tool_calls", None):
            return {
                **state,
                "tool_messages": tool_messages + [response],
            }

        # Final text reply
        reply = response.content.strip() if isinstance(response.content, str) else ""

        # Extract and strip the [IMG_CTX:...] tag if present
        imagen_contexto: str | None = None
        img_ctx_match = re.search(r"\[IMG_CTX:([^\]]+)\]", reply)
        if img_ctx_match:
            imagen_contexto = img_ctx_match.group(1).strip()
            reply = re.sub(r"\[IMG_CTX:[^\]]+\]\s*", "", reply).strip()

        uncertainty_phrases = [
            "i don't know", "i'm not sure", "i cannot", "i can't",
            "no sé", "no puedo", "no tengo información",
        ]
        confidence = 0.9
        if any(p in reply.lower() for p in uncertainty_phrases):
            confidence = 0.4

        # Check if the LLM replied with a menu JSON
        interactive_payload = parse_menu_reply(reply)
        # Use a human-readable content for DB storage when it's a menu
        stored_content = reply if not interactive_payload else reply

        return {
            **state,
            "bot_reply": stored_content,
            "interactive_payload": interactive_payload,
            "imagen_contexto": imagen_contexto,
            "confidence": confidence,
            "tool_messages": [],  # reset after final reply
        }

    return specialist_node


# ── Escalation decision ────────────────────────────────────────────────────────

def should_escalate(state: dict) -> Literal["escalate", "reply"]:
    intent = state.get("intent", "faq")
    confidence = state.get("confidence", 1.0)
    turns = state.get("turns", 0)
    max_turns = settings.AI_MAX_TURNS
    threshold = settings.AI_CONFIDENCE_THRESHOLD

    # Always honor an explicit user request for a human agent
    if intent == "escalate":
        return "escalate"
    # Guard auto-escalation (confidence/turns) on the first interaction
    if turns <= 1:
        return "reply"
    if confidence < threshold:
        return "escalate"
    if turns >= max_turns:
        return "escalate"
    return "reply"


# ── Route after classifier ─────────────────────────────────────────────────────

def route_intent(state: dict) -> Literal["faq", "sales", "support", "escalate"]:
    intent = state.get("intent", "faq")
    # Always route explicit escalation intents — do NOT guard on turns here.
    # The turns guard only applies to automatic escalation (confidence/max_turns),
    # which is handled inside should_escalate.
    return intent  # type: ignore[return-value]
