"""
LangGraph conversation graph with Azure OpenAI.

Graph flow (with tools):
  START → classifier → route_intent →
    specialist → tool_node (if tool_calls) → specialist (loop)
               → should_escalate → escalate | END
    escalate → END

State schema:
  messages              : list of {"role": "user"|"bot", "content": str}
  tenant_system_prompt  : str
  intent                : str
  bot_reply             : str
  confidence            : float
  turns                 : int
  needs_escalation      : bool
  lc_tools              : list  (LangChain StructuredTools, injected at runtime)
"""
from __future__ import annotations

import logging
from typing import Any, TypedDict

from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    classifier_node,
    make_specialist_node,
    route_intent,
    should_escalate,
)

logger = logging.getLogger(__name__)


# ── State ─────────────────────────────────────────────────────────────────────

class ChatState(TypedDict, total=False):
    messages: list[dict]
    tenant_system_prompt: str
    tenant_id: str                # UUID string of the tenant — used for RAG lookup
    conversation_id: str          # UUID string of the conversation — used for intent caching
    phone: str                    # WhatsApp number of the user (e.g. 573001234567)
    intent: str
    bot_reply: str
    confidence: float
    turns: int
    needs_escalation: bool
    lc_tools: list[Any]           # list[StructuredTool] — injected per invocation
    tool_messages: list[Any]      # internal LangChain messages for ToolNode loop
    interactive_payload: dict | None  # Meta interactive object when bot replies with a menu
    has_pending_image: bool       # True when there is an image awaiting user description
    imagen_contexto: str | None   # LLM-extracted description of the pending image
    tokens_in: int                # prompt tokens consumed this turn (accumulated over tool loops)
    tokens_out: int               # completion tokens produced this turn


# ── Escalation node ───────────────────────────────────────────────────────────

async def escalate_node(state: ChatState) -> ChatState:
    logger.info("Escalating conversation to human agent")
    return {
        **state,  # type: ignore[misc]
        "needs_escalation": True,
        "bot_reply": state.get(
            "bot_reply",
            "Voy a transferirte con un agente humano. Un momento por favor.",
        ),
    }


# ── Route after specialist: tool call or done ─────────────────────────────────

def _route_after_specialist(state: ChatState) -> str:
    """If the LLM emitted tool_calls, go to tool_node; otherwise check escalation."""
    pending = state.get("tool_messages", [])
    if pending and hasattr(pending[-1], "tool_calls") and pending[-1].tool_calls:
        return "tool_node"
    return should_escalate(state)


# ── Graph definition ──────────────────────────────────────────────────────────

def _make_tool_executor(tools: list[StructuredTool]) -> Any:
    """
    Custom tool executor node.

    LangGraph's built-in ToolNode expects the AIMessage in state["messages"],
    but our ChatState keeps conversation history as plain dicts in state["messages"]
    and the LangChain AIMessage (with tool_calls) in state["tool_messages"].
    This node reads from there instead.
    """
    tool_map = {t.name: t for t in tools}

    async def tool_executor(state: ChatState) -> ChatState:
        tool_messages: list[Any] = list(state.get("tool_messages", []))

        # Find the last AIMessage that has pending tool calls
        last_ai = None
        for msg in reversed(tool_messages):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                last_ai = msg
                break

        if last_ai is None:
            logger.warning("tool_executor: no AIMessage with tool_calls found")
            return state  # type: ignore[return-value]

        results: list[ToolMessage] = []
        for tc in last_ai.tool_calls:
            tool = tool_map.get(tc["name"])
            if tool is None:
                content = f"Herramienta '{tc['name']}' no encontrada."
            else:
                try:
                    raw = await tool.ainvoke(tc["args"])
                    content = str(raw)
                except Exception as exc:
                    logger.error("Tool %s execution error: %s", tc["name"], exc)
                    content = f"Error al ejecutar la herramienta: {exc}"
            results.append(ToolMessage(content=content, tool_call_id=tc["id"]))

        return {**state, "tool_messages": tool_messages + results}  # type: ignore[misc]

    return tool_executor


def build_graph(tools: list[StructuredTool] | None = None) -> Any:
    tools = tools or []
    specialist_node = make_specialist_node(tools)
    tool_executor = _make_tool_executor(tools) if tools else None

    graph = StateGraph(ChatState)

    graph.add_node("classifier", classifier_node)
    graph.add_node("specialist", specialist_node)
    graph.add_node("escalate", escalate_node)

    if tool_executor:
        graph.add_node("tool_node", tool_executor)
        graph.add_edge("tool_node", "specialist")

    graph.add_edge(START, "classifier")

    graph.add_conditional_edges(
        "classifier",
        route_intent,
        {
            "faq": "specialist",
            "sales": "specialist",
            "support": "specialist",
            "escalate": "escalate",
        },
    )

    edges: dict[str, str] = {"escalate": "escalate", "reply": END}
    if tool_executor:
        edges["tool_node"] = "tool_node"

    graph.add_conditional_edges("specialist", _route_after_specialist, edges)
    graph.add_edge("escalate", END)

    return graph.compile()


# ── Public API ────────────────────────────────────────────────────────────────

async def run_graph(
    messages: list[dict],
    tenant_system_prompt: str = "",
    tenant_id: str = "",
    conversation_id: str = "",
    turns: int = 0,
    tools: list[StructuredTool] | None = None,
    phone: str = "",
    has_pending_image: bool = False,
) -> dict:
    """
    Run the conversation graph and return the final state.

    Args:
        messages: Full conversation history [{"role": "user"|"bot", "content": str}, ...]
        tenant_system_prompt: Tenant-specific system prompt / knowledge base
        tenant_id: UUID string of the tenant (used for RAG knowledge lookup)
        turns: Current turn count for this conversation
        phone: WhatsApp phone number of the user
        tools: LangChain StructuredTools loaded for this tenant (may be empty)

    Returns:
        dict with keys: bot_reply, intent, confidence, needs_escalation
    """
    graph = build_graph(tools or [])

    initial_state: ChatState = {
        "messages": messages,
        "tenant_system_prompt": tenant_system_prompt,
        "tenant_id": tenant_id,
        "conversation_id": conversation_id,
        "phone": phone,
        "turns": turns,
        "needs_escalation": False,
        "lc_tools": tools or [],
        "tool_messages": [],
        "has_pending_image": has_pending_image,
        "imagen_contexto": None,
        "tokens_in": 0,
        "tokens_out": 0,
    }

    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("LangGraph error: %s", exc)
        return {
            "bot_reply": "Lo siento, ocurrió un error. Un agente te atenderá pronto.",
            "intent": "escalate",
            "confidence": 0.0,
            "needs_escalation": True,
        }

    return {
        "bot_reply": final_state.get("bot_reply", ""),
        "intent": final_state.get("intent", "unknown"),
        "confidence": final_state.get("confidence", 0.0),
        "needs_escalation": final_state.get("needs_escalation", False),
        "interactive_payload": final_state.get("interactive_payload"),
        "imagen_contexto": final_state.get("imagen_contexto"),
        "tokens_in": final_state.get("tokens_in", 0),
        "tokens_out": final_state.get("tokens_out", 0),
    }
