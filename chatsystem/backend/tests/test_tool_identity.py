import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from app.models.agent_tool import ToolType
from app.services import tool_engine


class FakeRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeDb:
    def __init__(self, identity_phone=None, tools=()):
        self.identity_phone = identity_phone
        self.tools = list(tools)
        self.scalar_calls = []
        self.scalars_calls = []

    async def scalar(self, statement, params=None):
        self.scalar_calls.append((statement, params))
        return self.identity_phone

    async def scalars(self, statement):
        self.scalars_calls.append(statement)
        return FakeRows(self.tools)


def sql_phone_tool(name="personal"):
    return SimpleNamespace(
        name=name,
        tool_type=ToolType.SQL,
        sql_params=["phone"],
        sql_query="SELECT * FROM clientes WHERE phone = :phone",
        sql_dsn="postgresql+asyncpg://example",
    )


def static_tool(name="publica"):
    return SimpleNamespace(
        name=name,
        tool_type=ToolType.STATIC,
        sql_params=None,
        sql_query=None,
        sql_dsn=None,
    )


class ToolIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_phone_is_used_without_contact_lookup(self):
        db = FakeDb()

        result = await tool_engine.resolve_identity_phone(db, "573001234567")

        self.assertEqual(result, "573001234567")
        self.assertEqual(db.scalar_calls, [])

    async def test_bsuid_resolves_to_stored_real_phone(self):
        db = FakeDb(identity_phone="573009876543")

        result = await tool_engine.resolve_identity_phone(
            db, "CO.1949266959121697"
        )

        self.assertEqual(result, "573009876543")
        self.assertEqual(
            db.scalar_calls[0][1],
            {"bsuid": "CO.1949266959121697"},
        )

    async def test_bsuid_without_contact_has_no_identity_phone(self):
        db = FakeDb(identity_phone=None)

        result = await tool_engine.resolve_identity_phone(
            db, "CO.1949266959121697"
        )

        self.assertIsNone(result)

    async def test_personal_tool_receives_resolved_phone_not_bsuid(self):
        db = FakeDb(
            identity_phone="573009876543",
            tools=[sql_phone_tool()],
        )
        captured_contexts = []

        def build(tool, context):
            captured_contexts.append(dict(context))
            return tool.name

        with patch.object(tool_engine, "_build_tool", side_effect=build):
            result = await tool_engine.load_tools(
                db=db,
                tenant_id=uuid.uuid4(),
                phone="CO.1949266959121697",
                conversation_id=str(uuid.uuid4()),
                tenant_slug="mauriciovelez",
            )

        self.assertEqual(result, ["personal"])
        self.assertEqual(captured_contexts[0]["phone"], "573009876543")
        self.assertNotIn("CO.1949266959121697", captured_contexts[0].values())

    async def test_missing_identity_hides_only_phone_dependent_tools(self):
        db = FakeDb(
            identity_phone=None,
            tools=[sql_phone_tool(), static_tool()],
        )
        built_names = []

        def build(tool, context):
            built_names.append(tool.name)
            self.assertNotIn("phone", context)
            return tool.name

        with patch.object(tool_engine, "_build_tool", side_effect=build):
            result = await tool_engine.load_tools(
                db=db,
                tenant_id=uuid.uuid4(),
                phone="CO.1949266959121697",
                conversation_id=str(uuid.uuid4()),
                tenant_slug="mauriciovelez",
            )

        self.assertEqual(result, ["publica"])
        self.assertEqual(built_names, ["publica"])


if __name__ == "__main__":
    unittest.main()
