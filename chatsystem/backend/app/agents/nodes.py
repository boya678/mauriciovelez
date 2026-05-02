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

import logging
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

_CLASSIFIER_SYSTEM = """You are a conversation classifier for a customer support system.
Given the conversation history, classify the user's intent into ONE category:
- faq        : general questions, greetings, information requests
- sales      : pricing, purchasing, product interest, upgrades, promotions
- support    : technical problems, complaints, refund requests, account issues
- escalate   : user is angry, request impossible for AI, asks for human agent

Respond with ONLY the category word (faq / sales / support / escalate).
Do NOT include any explanation."""


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
        "You are a helpful FAQ assistant. Answer the user's question clearly "
        "and concisely based on the business context provided. If you don't know "
        "the answer, say so honestly rather than making something up. "
        "Keep responses under 3 paragraphs. Be friendly and professional."
    ),
    "sales": (
        "You are a helpful sales assistant. Your goal is to understand what the "
        "customer is looking for and provide information about products, pricing, "
        "and available promotions. Be enthusiastic but not pushy. If the customer "
        "is ready to purchase, guide them to the next step. "
        "Keep responses concise and to the point."
    ),
    "support": (
        "You are a customer support specialist. Help the user resolve their issue "
        "step by step. Gather all necessary information before proposing solutions. "
        "Be empathetic and patient. If the issue requires access to internal systems "
        "or a human decision, acknowledge this and offer to escalate. "
        "Keep responses clear and structured."
    ),
}

_DEFAULT_PROMPT = _INTENT_PROMPTS["faq"]


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
        system_content = base_prompt
        if tenant_prompt:
            system_content += f"\n\nBusiness-specific knowledge:\n{tenant_prompt}"

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

        uncertainty_phrases = [
            "i don't know", "i'm not sure", "i cannot", "i can't",
            "no sé", "no puedo", "no tengo información",
        ]
        confidence = 0.9
        if any(p in reply.lower() for p in uncertainty_phrases):
            confidence = 0.4

        return {
            **state,
            "bot_reply": reply,
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

    # Never escalate on the very first interaction — let the bot reply at least once
    if turns <= 1:
        return "reply"
    if intent == "escalate":
        return "escalate"
    if confidence < threshold:
        return "escalate"
    if turns >= max_turns:
        return "escalate"
    return "reply"


# ── Route after classifier ─────────────────────────────────────────────────────

def route_intent(state: dict) -> Literal["faq", "sales", "support", "escalate"]:
    intent = state.get("intent", "faq")
    turns = state.get("turns", 0)
    # Never escalate on the very first interaction — let the bot reply at least once
    if turns <= 1 and intent == "escalate":
        return "faq"
    return intent  # type: ignore[return-value]
