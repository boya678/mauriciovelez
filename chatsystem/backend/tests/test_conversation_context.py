import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents import nodes
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
    def __init__(self, intent="support"):
        self.intent = intent
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return SimpleNamespace(
            content=self.intent,
            usage_metadata={"input_tokens": 10, "output_tokens": 1},
        )


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

    async def test_classifier_receives_all_twelve_current_session_messages(self):
        messages = [
            {
                "role": "user" if index % 2 == 0 else "bot",
                "content": f"contexto-{index}",
            }
            for index in range(12)
        ]
        llm = CapturingLlm(intent="escalate")

        with patch.object(nodes, "_get_llm", return_value=llm):
            result = await nodes.classifier_node({
                "messages": messages,
                "conversation_id": "conversation-test",
                "tenant_system_prompt": "Política del tenant",
                "turns": 6,
                "tokens_in": 0,
                "tokens_out": 0,
            })

        self.assertEqual(result["intent"], "escalate")
        self.assertEqual(result["turns"], 7)
        self.assertIsInstance(llm.messages[0], SystemMessage)
        self.assertIsInstance(llm.messages[1], SystemMessage)
        conversation_messages = llm.messages[2:]
        self.assertEqual(len(conversation_messages), 12)
        self.assertEqual(conversation_messages[0].content, "contexto-0")
        self.assertEqual(conversation_messages[-1].content, "contexto-11")
        self.assertIsInstance(conversation_messages[0], HumanMessage)
        self.assertIsInstance(conversation_messages[1], AIMessage)


if __name__ == "__main__":
    unittest.main()
