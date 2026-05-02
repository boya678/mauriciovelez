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

from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

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
    intent: str
    bot_reply: str
    confidence: float
    turns: int
    needs_escalation: bool
    lc_tools: list[Any]           # list[StructuredTool] — injected per invocation
    tool_messages: list[Any]      # internal LangChain messages for ToolNode loop


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

def build_graph(tools: list[StructuredTool] | None = None) -> Any:
    tools = tools or []
    specialist_node = make_specialist_node(tools)
    tool_node = ToolNode(tools) if tools else None

    graph = StateGraph(ChatState)

    graph.add_node("classifier", classifier_node)
    graph.add_node("specialist", specialist_node)
    graph.add_node("escalate", escalate_node)

    if tool_node:
        graph.add_node("tool_node", tool_node)
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
    if tool_node:
        edges["tool_node"] = "tool_node"

    graph.add_conditional_edges("specialist", _route_after_specialist, edges)
    graph.add_edge("escalate", END)

    return graph.compile()


# ── Public API ────────────────────────────────────────────────────────────────

async def run_graph(
    messages: list[dict],
    tenant_system_prompt: str = "",
    turns: int = 0,
    tools: list[StructuredTool] | None = None,
) -> dict:
    """
    Run the conversation graph and return the final state.

    Args:
        messages: Full conversation history [{"role": "user"|"bot", "content": str}, ...]
        tenant_system_prompt: Tenant-specific system prompt / knowledge base
        turns: Current turn count for this conversation
        tools: LangChain StructuredTools loaded for this tenant (may be empty)

    Returns:
        dict with keys: bot_reply, intent, confidence, needs_escalation
    """
    graph = build_graph(tools or [])

    initial_state: ChatState = {
        "messages": messages,
        "tenant_system_prompt": tenant_system_prompt,
        "turns": turns,
        "needs_escalation": False,
        "lc_tools": tools or [],
        "tool_messages": [],
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
    }
