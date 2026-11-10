import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool

from app.agents import nodes
from app.agents.graph import run_graph
from app.models.message import SenderType
from app.workers import ai_worker


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeHistoryDb:
    def __init__(self, context_started_at, rows):
        self.context_started_at = context_started_at
        self.rows = rows
        self.history_statement = None

    async def scalar(self, statement):
        return self.context_started_at

    async def scalars(self, statement):
        self.history_statement = statement
        return FakeScalarResult(self.rows)


class CapturingLlm:
    def __init__(self, *responses):
        self.responses = iter(responses or [AIMessage(
            content="Respuesta de prueba",
            usage_metadata={"input_tokens": 10, "output_tokens": 1, "total_tokens": 11},
        )])
        self.messages = None
        self.calls = []
        self.tools = []

    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, messages):
        self.messages = messages
        self.calls.append(messages)
        return next(self.responses)


class ConversationContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_uses_context_boundary_and_latest_twelve(self):
        context_started_at = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
        conversation_id = uuid.uuid4()
        chronological = [
            SimpleNamespace(
                id=uuid.uuid4(),
                sender_type=SenderType.USER if index % 2 == 0 else SenderType.BOT,
                content=f"mensaje-{index}",
                message_type="text",
                imagen_descripcion=None,
            )
            for index in range(12)
        ]
        db = FakeHistoryDb(context_started_at, list(reversed(chronological)))

        history, user_turns = await ai_worker._load_history(db, conversation_id)

        self.assertEqual(len(history), 12)
        self.assertEqual([item["content"] for item in history], [
            f"mensaje-{index}" for index in range(12)
        ])
        self.assertEqual(user_turns, 6)
        self.assertEqual(db.history_statement._limit_clause.value, 12)
        compiled = db.history_statement.compile()
        self.assertIn(context_started_at, compiled.params.values())

    async def test_single_agent_receives_history_and_business_rules_in_one_call(self):
        messages = [
            {
                "role": "user" if index % 2 == 0 else "bot",
                "content": f"contexto-{index}",
            }
            for index in range(12)
        ]
        llm = CapturingLlm()

        with patch.object(nodes, "_get_llm", return_value=llm):
            result = await run_graph(
                messages=messages,
                conversation_id="conversation-test",
                tenant_system_prompt="Política del tenant",
                turns=6,
            )

        self.assertEqual(result["bot_reply"], "Respuesta de prueba")
        self.assertFalse(result["needs_escalation"])
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(result["tokens_in"], 10)
        self.assertEqual(result["tokens_out"], 1)
        self.assertEqual([tool.name for tool in llm.tools], [nodes.HUMAN_TRANSFER_TOOL_NAME])
        self.assertIsInstance(llm.messages[0], SystemMessage)
        self.assertIsInstance(llm.messages[1], SystemMessage)
        self.assertIn("Política del tenant", llm.messages[1].content)
        conversation_messages = [
            message for message in llm.messages if not isinstance(message, SystemMessage)
        ]
        self.assertEqual(len(conversation_messages), 12)
        self.assertEqual(conversation_messages[0].content, "contexto-0")
        self.assertEqual(conversation_messages[-1].content, "contexto-11")
        self.assertIsInstance(conversation_messages[0], HumanMessage)
        self.assertIsInstance(conversation_messages[1], AIMessage)

    async def test_business_tool_still_runs_then_agent_answers(self):
        calls = []

        async def consult_account():
            """Consulta el estado de la cuenta."""
            calls.append("consulted")
            return "Suscripcion activa"

        account_tool = StructuredTool.from_function(coroutine=consult_account)
        llm = CapturingLlm(
            AIMessage(content="", tool_calls=[{
                "id": "account-call", "name": "consult_account", "args": {},
            }], usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}),
            AIMessage(content="Tu suscripcion esta activa.", usage_metadata={
                "input_tokens": 20, "output_tokens": 4, "total_tokens": 24,
            }),
        )

        with patch.object(nodes, "_get_llm", return_value=llm):
            result = await run_graph(
                messages=[{"role": "user", "content": "Mi suscripcion sigue activa?"}],
                tools=[account_tool],
            )

        self.assertEqual(calls, ["consulted"])
        self.assertEqual(len(llm.calls), 2)
        self.assertFalse(result["needs_escalation"])
        self.assertEqual(result["tokens_in"], 30)
        self.assertEqual(result["tokens_out"], 6)
        self.assertTrue(any(
            isinstance(message, ToolMessage) and message.content == "Suscripcion activa"
            for message in llm.calls[1]
        ))

    async def test_human_request_transfers_on_first_turn_without_second_model_call(self):
        notice = "Voy a transferirte con un asesor humano. Un momento, por favor."
        llm = CapturingLlm(AIMessage(content="", tool_calls=[{
            "id": "handoff-call", "name": nodes.HUMAN_TRANSFER_TOOL_NAME,
            "args": {"mensaje": notice},
        }]))

        with patch.object(nodes, "_get_llm", return_value=llm):
            result = await run_graph(messages=[{
                "role": "user", "content": "Necesito que me atienda una persona",
            }])

        self.assertEqual(len(llm.calls), 1)
        self.assertTrue(result["needs_escalation"])
        self.assertEqual(result["intent"], "escalate")
        self.assertEqual(result["bot_reply"], notice)
        self.assertIsNone(result["interactive_payload"])

    async def test_transfer_takes_priority_over_other_tool_calls(self):
        calls = []

        async def consult_account():
            """Consulta el estado de la cuenta."""
            calls.append("consulted")
            return "Suscripcion activa"

        llm = CapturingLlm(AIMessage(content="", tool_calls=[
            {"id": "account-call", "name": "consult_account", "args": {}},
            {"id": "handoff-call", "name": nodes.HUMAN_TRANSFER_TOOL_NAME,
             "args": {"mensaje": "Un asesor humano continuara con tu solicitud."}},
        ]))

        with patch.object(nodes, "_get_llm", return_value=llm):
            result = await run_graph(
                messages=[{"role": "user", "content": "Quiero hablar con un asesor"}],
                tools=[StructuredTool.from_function(coroutine=consult_account)],
            )

        self.assertEqual(calls, [])
        self.assertEqual(len(llm.calls), 1)
        self.assertTrue(result["needs_escalation"])

    async def test_pending_image_keeps_description_tool_and_instructions(self):
        descriptions = []

        async def guardar_descripcion_imagen(description: str):
            """Registra el proposito de la imagen pendiente."""
            descriptions.append(description)
            return "Descripcion registrada"

        llm = CapturingLlm(
            AIMessage(content="", tool_calls=[{
                "id": "image-call", "name": "guardar_descripcion_imagen",
                "args": {"description": "Pago para activar plan VIP"},
            }]),
            AIMessage(content="Registramos que tu imagen corresponde al plan VIP."),
        )

        with patch.object(nodes, "_get_llm", return_value=llm):
            result = await run_graph(
                messages=[
                    {"role": "user", "content": "[IMAGEN sin describir aun]"},
                    {"role": "user", "content": "pago_vip"},
                ],
                has_pending_image=True,
                tools=[StructuredTool.from_function(coroutine=guardar_descripcion_imagen)],
            )

        self.assertEqual(descriptions, ["Pago para activar plan VIP"])
        self.assertEqual(len(llm.calls), 2)
        self.assertFalse(result["needs_escalation"])
        self.assertTrue(any(
            isinstance(message, SystemMessage) and "IMAGEN PENDIENTE" in message.content
            for message in llm.calls[0]
        ))

    async def test_interactive_menu_still_works_with_one_agent(self):
        llm = CapturingLlm(AIMessage(content=(
            '{"menu_type":"buttons","body":"Elige una opcion",'
            '"buttons":[{"id":"vip","title":"VIP"},'
            '{"id":"free","title":"Gratis"}]}'
        )))

        with patch.object(nodes, "_get_llm", return_value=llm):
            result = await run_graph(messages=[{
                "role": "user", "content": "Que planes tienen?",
            }])

        self.assertEqual(len(llm.calls), 1)
        self.assertFalse(result["needs_escalation"])
        self.assertEqual(result["interactive_payload"]["type"], "button")
        self.assertEqual(len(result["interactive_payload"]["action"]["buttons"]), 2)

    async def test_turn_counter_preserves_low_confidence_guard(self):
        for previous_turns, expected_transfer in ((0, False), (1, False), (2, True)):
            with self.subTest(previous_turns=previous_turns):
                llm = CapturingLlm(AIMessage(content="No tengo información suficiente."))
                with patch.object(nodes, "_get_llm", return_value=llm):
                    result = await run_graph(
                        messages=[{"role": "user", "content": "Puedes resolverlo?"}],
                        turns=previous_turns,
                    )

                self.assertEqual(len(llm.calls), 1)
                self.assertEqual(result["needs_escalation"], expected_transfer)


if __name__ == "__main__":
    unittest.main()
