import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException

from app.api import conversations as conversations_api
from app.agents.nodes import should_escalate
from app.models.conversation import ConversationStatus
from app.models.message import MessageStatus, SenderType
from app.services import round_robin
from app.workers import ai_worker, assignment_worker, conversation_lifecycle, outgoing_worker


class FakeSession:
    def __init__(self, scalar_results=(), execute_results=()):
        self._scalar_results = iter(scalar_results)
        self._execute_results = list(execute_results)
        self.added = []
        self.executed = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, *args, **kwargs):
        self.executed.append((args, kwargs))
        if self._execute_results:
            return self._execute_results.pop(0)
        return SimpleNamespace()

    async def scalar(self, *args, **kwargs):
        try:
            return next(self._scalar_results)
        except StopIteration as exc:
            raise AssertionError("Unexpected db.scalar() call") from exc

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, value):
        return None


class FakeSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class SessionFactory:
    def __init__(self, *sessions):
        self._sessions = iter(sessions)

    def __call__(self, *args, **kwargs):
        try:
            return FakeSessionContext(next(self._sessions))
        except StopIteration as exc:
            raise AssertionError("Unexpected database session") from exc


def conversation(**overrides):
    now = datetime.now(timezone.utc)
    values = {
        "id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "phone": "573001234567",
        "username": None,
        "bsuid": None,
        "status": ConversationStatus.BOT_ACTIVE,
        "assigned_agent_id": None,
        "created_at": now - timedelta(hours=2),
        "last_user_message_at": now - timedelta(hours=1),
        "last_activity_at": now - timedelta(minutes=40),
        "idle_warning_sent_at": None,
        "handoff_notice_sent_at": None,
        "updated_at": now - timedelta(minutes=40),
        "closed_at": None,
        "tags": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def message(conversation_id, **overrides):
    values = {
        "id": uuid.uuid4(),
        "conversation_id": conversation_id,
        "sender_type": SenderType.BOT,
        "content": "Respuesta",
        "message_type": "text",
        "status": MessageStatus.PENDING,
        "created_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def tenant(**overrides):
    values = {
        "id": uuid.uuid4(),
        "slug": "prueba",
        "whatsapp_phone_id": "phone-id",
        "whatsapp_token": "token",
        "ai_system_prompt": "",
        "image_menu_payload": None,
        "active": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def handoff_data(conv, msg):
    return {
        "tenant_id": str(conv.tenant_id),
        "tenant_slug": "prueba",
        "phone": conv.phone,
        "message_id": str(msg.id),
        "content": "Te atendera un agente humano.",
        "phone_id": "phone-id",
        "token": "token",
        "handoff_after_send": True,
        "conversation_id": str(conv.id),
    }


class HandoffPolicyTests(unittest.TestCase):
    def test_explicit_escalation_always_escalates(self):
        self.assertEqual(
            should_escalate({"intent": "escalate", "confidence": 1.0, "turns": 1}),
            "escalate",
        )

    def test_low_confidence_does_not_escalate_first_two_turns(self):
        for turns in (1, 2):
            with self.subTest(turns=turns):
                self.assertEqual(
                    should_escalate({"intent": "support", "confidence": 0.1, "turns": turns}),
                    "reply",
                )

    def test_low_confidence_escalates_after_guard_turns(self):
        self.assertEqual(
            should_escalate({"intent": "support", "confidence": 0.1, "turns": 3}),
            "escalate",
        )

    def test_handoff_notice_is_added_to_ambiguous_reply(self):
        original = "El equipo validara tu informacion."
        result = ai_worker._ensure_handoff_notice(original)
        self.assertIn(original, result)
        self.assertIn(ai_worker.settings.HUMAN_HANDOFF_NOTICE_TEXT, result)

    def test_explicit_handoff_reply_is_not_duplicated(self):
        original = "Voy a transferirte con un agente para continuar."
        self.assertEqual(ai_worker._ensure_handoff_notice(original), original)

    def test_empty_handoff_reply_uses_configured_notice(self):
        self.assertEqual(
            ai_worker._ensure_handoff_notice(""),
            ai_worker.settings.HUMAN_HANDOFF_NOTICE_TEXT,
        )

    def test_all_handoff_window_checks_agree(self):
        now = datetime.now(timezone.utc)
        for check in (
            assignment_worker._window_open,
            outgoing_worker._window_open,
        ):
            with self.subTest(check=check.__module__):
                self.assertTrue(check(now - timedelta(hours=23)))
                self.assertFalse(check(now - timedelta(hours=25)))

    def test_warning_requires_enough_time_to_finish_grace(self):
        now = datetime.now(timezone.utc)
        self.assertTrue(
            conversation_lifecycle._window_open(
                now - timedelta(hours=23, minutes=40), required_minutes=10
            )
        )
        self.assertFalse(
            conversation_lifecycle._window_open(
                now - timedelta(hours=23, minutes=55), required_minutes=10
            )
        )


class AiOwnershipRaceTests(unittest.IsolatedAsyncioTestCase):
    async def _run_publish_failure(self, needs_escalation: bool):
        conv_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        conv = conversation(
            id=conv_id,
            tenant_id=tenant_id,
            status=ConversationStatus.BOT_ACTIVE,
        )
        db = FakeSession([
            MessageStatus.PROCESSING,
            tenant(id=tenant_id),
            conv,
            conv,
        ])
        redis = SimpleNamespace(lindex=AsyncMock(return_value=None))
        add_to_stream = AsyncMock(side_effect=RuntimeError("Redis unavailable"))

        with (
            patch.object(ai_worker, "make_tenant_session", SessionFactory(db)),
            patch.object(ai_worker, "_load_history", AsyncMock(return_value=([{"role": "user", "content": "hola"}], 1))),
            patch.object(ai_worker, "load_tools", AsyncMock(return_value=[])),
            patch.object(
                ai_worker,
                "run_graph",
                AsyncMock(return_value={
                    "bot_reply": (
                        "Voy a transferirte con un agente para continuar."
                        if needs_escalation
                        else "Hola, te ayudo."
                    ),
                    "needs_escalation": needs_escalation,
                    "interactive_payload": None,
                    "tokens_in": 0,
                    "tokens_out": 0,
                }),
            ),
            patch.object(ai_worker, "xadd", add_to_stream),
        ):
            with self.assertRaises(RuntimeError):
                await ai_worker._process_entry(
                    redis,
                    "1-0",
                    {
                        "tenant_id": str(tenant_id),
                        "tenant_slug": "prueba",
                        "conversation_id": str(conv_id),
                        "message_id": str(uuid.uuid4()),
                        "phone": conv.phone,
                    },
                )

        status_updates = [
            args[0].compile().params.get("status")
            for args, _ in db.executed
            if args and hasattr(args[0], "compile")
        ]
        self.assertIn(MessageStatus.ERROR, status_updates)
        self.assertIn(MessageStatus.PROCESSING, status_updates)
        self.assertEqual(conv.status, ConversationStatus.BOT_ACTIVE)
        self.assertEqual(db.commits, 3)

    async def test_normal_reply_publish_failure_restores_ai_entry(self):
        await self._run_publish_failure(needs_escalation=False)

    async def test_handoff_publish_failure_restores_ai_entry(self):
        await self._run_publish_failure(needs_escalation=True)

    async def test_agent_takeover_discards_inflight_ai_result(self):
        conv_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        initial_conv = conversation(
            id=conv_id,
            tenant_id=tenant_id,
            status=ConversationStatus.BOT_ACTIVE,
        )
        taken_conv = conversation(
            id=conv_id,
            tenant_id=tenant_id,
            status=ConversationStatus.HUMAN_ACTIVE,
        )
        tenant_row = tenant(id=tenant_id)
        db = FakeSession([
            MessageStatus.PROCESSING,
            tenant_row,
            initial_conv,
            taken_conv,
        ])
        redis = SimpleNamespace(lindex=AsyncMock(return_value=None))
        add_to_stream = AsyncMock()

        with (
            patch.object(ai_worker, "make_tenant_session", SessionFactory(db)),
            patch.object(ai_worker, "_load_history", AsyncMock(return_value=([{"role": "user", "content": "hola"}], 1))),
            patch.object(ai_worker, "load_tools", AsyncMock(return_value=[])),
            patch.object(
                ai_worker,
                "run_graph",
                AsyncMock(return_value={
                    "bot_reply": "Respuesta tardia",
                    "needs_escalation": False,
                    "interactive_payload": None,
                    "tokens_in": 0,
                    "tokens_out": 0,
                }),
            ),
            patch.object(ai_worker, "xadd", add_to_stream),
        ):
            await ai_worker._process_entry(
                redis,
                "1-0",
                {
                    "tenant_id": str(tenant_id),
                    "tenant_slug": "prueba",
                    "conversation_id": str(conv_id),
                    "message_id": str(uuid.uuid4()),
                    "phone": initial_conv.phone,
                },
            )

        add_to_stream.assert_not_awaited()
        self.assertEqual(db.added, [])
        self.assertEqual(db.commits, 2)


class OutgoingHandoffTests(unittest.IsolatedAsyncioTestCase):
    def _redis(self, attempts=1):
        return SimpleNamespace(
            set=AsyncMock(return_value=True),
            incr=AsyncMock(return_value=attempts),
            expire=AsyncMock(),
            delete=AsyncMock(),
            eval=AsyncMock(return_value=1),
        )

    async def test_successful_meta_send_enables_handoff(self):
        conv = conversation()
        msg = message(conv.id)
        precheck_db = FakeSession([msg, conv])
        completion_db = FakeSession([msg, conv])
        send = AsyncMock()
        add_to_stream = AsyncMock()
        publish = AsyncMock()
        redis = self._redis()

        with (
            patch.object(
                outgoing_worker,
                "make_tenant_session",
                SessionFactory(FakeSession([msg]), precheck_db, completion_db),
            ),
            patch.object(outgoing_worker, "send_text_message", send),
            patch.object(outgoing_worker, "xadd", add_to_stream),
            patch.object(outgoing_worker.manager, "publish", publish),
        ):
            completed = await outgoing_worker._process_entry(redis, "1-0", handoff_data(conv, msg))

        self.assertTrue(completed)
        send.assert_awaited_once()
        add_to_stream.assert_awaited_once()
        self.assertEqual(
            add_to_stream.await_args.args[1], outgoing_worker.HUMAN_ASSIGN_STREAM
        )
        self.assertEqual(conv.status, ConversationStatus.WAITING_HUMAN)
        self.assertIsNotNone(conv.handoff_notice_sent_at)
        publish.assert_awaited_once()

    async def test_transient_meta_failure_retries_without_handoff(self):
        conv = conversation()
        msg = message(conv.id)
        precheck_db = FakeSession([msg, conv])
        completion_db = FakeSession()
        send = AsyncMock(side_effect=RuntimeError("Meta unavailable"))
        add_to_stream = AsyncMock()
        publish = AsyncMock()
        redis = self._redis(attempts=1)

        with (
            patch.object(
                outgoing_worker,
                "make_tenant_session",
                SessionFactory(FakeSession([msg]), precheck_db, completion_db),
            ),
            patch.object(outgoing_worker, "send_text_message", send),
            patch.object(outgoing_worker, "xadd", add_to_stream),
            patch.object(outgoing_worker.manager, "publish", publish),
        ):
            completed = await outgoing_worker._process_entry(redis, "1-0", handoff_data(conv, msg))

        self.assertFalse(completed)
        send.assert_awaited_once()
        add_to_stream.assert_not_awaited()
        publish.assert_not_awaited()
        self.assertEqual(conv.status, ConversationStatus.BOT_ACTIVE)
        self.assertIsNone(conv.handoff_notice_sent_at)
        status_updates = [
            args[0].compile().params.get("status")
            for args, _ in completion_db.executed
            if args and hasattr(args[0], "compile")
        ]
        self.assertIn(MessageStatus.PENDING, status_updates)
        redis.incr.assert_awaited_once()
        redis.expire.assert_awaited_once()

    async def test_meta_http_500_retries_without_handoff(self):
        conv = conversation()
        msg = message(conv.id)
        precheck_db = FakeSession([msg, conv])
        completion_db = FakeSession()
        request = httpx.Request("POST", "https://graph.facebook.com/messages")
        response = httpx.Response(500, request=request, text="temporary")
        send = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "server error", request=request, response=response
            )
        )
        redis = self._redis(attempts=1)

        with (
            patch.object(
                outgoing_worker,
                "make_tenant_session",
                SessionFactory(FakeSession([msg]), precheck_db, completion_db),
            ),
            patch.object(outgoing_worker, "send_text_message", send),
        ):
            completed = await outgoing_worker._process_entry(
                redis, "1-0", handoff_data(conv, msg)
            )

        self.assertFalse(completed)
        self.assertEqual(conv.status, ConversationStatus.BOT_ACTIVE)
        redis.incr.assert_awaited_once()

    async def test_meta_http_400_is_terminal_without_handoff(self):
        conv = conversation()
        msg = message(conv.id)
        precheck_db = FakeSession([msg, conv])
        completion_db = FakeSession()
        request = httpx.Request("POST", "https://graph.facebook.com/messages")
        response = httpx.Response(400, request=request, text="invalid request")
        send = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "client error", request=request, response=response
            )
        )
        redis = self._redis(attempts=1)

        with (
            patch.object(
                outgoing_worker,
                "make_tenant_session",
                SessionFactory(FakeSession([msg]), precheck_db, completion_db),
            ),
            patch.object(outgoing_worker, "send_text_message", send),
        ):
            completed = await outgoing_worker._process_entry(
                redis, "1-0", handoff_data(conv, msg)
            )

        self.assertTrue(completed)
        self.assertEqual(conv.status, ConversationStatus.BOT_ACTIVE)
        redis.incr.assert_not_awaited()
        status_updates = [
            args[0].compile().params.get("status")
            for args, _ in completion_db.executed
            if args and hasattr(args[0], "compile")
        ]
        self.assertIn(MessageStatus.ERROR, status_updates)

    async def test_exhausted_meta_failure_is_terminal_without_handoff(self):
        conv = conversation()
        msg = message(conv.id)
        precheck_db = FakeSession([msg, conv])
        completion_db = FakeSession()
        send = AsyncMock(side_effect=RuntimeError("Meta unavailable"))
        add_to_stream = AsyncMock()
        redis = self._redis(attempts=outgoing_worker.settings.OUTGOING_MAX_RETRIES)

        with (
            patch.object(
                outgoing_worker,
                "make_tenant_session",
                SessionFactory(FakeSession([msg]), precheck_db, completion_db),
            ),
            patch.object(outgoing_worker, "send_text_message", send),
            patch.object(outgoing_worker, "xadd", add_to_stream),
        ):
            completed = await outgoing_worker._process_entry(
                redis, "1-0", handoff_data(conv, msg)
            )

        self.assertTrue(completed)
        add_to_stream.assert_not_awaited()
        self.assertEqual(conv.status, ConversationStatus.BOT_ACTIVE)
        status_updates = [
            args[0].compile().params.get("status")
            for args, _ in completion_db.executed
            if args and hasattr(args[0], "compile")
        ]
        self.assertIn(MessageStatus.ERROR, status_updates)
        redis.delete.assert_awaited_once()

    async def test_closed_24h_window_never_sends_or_assigns(self):
        conv = conversation(
            last_user_message_at=datetime.now(timezone.utc) - timedelta(hours=25)
        )
        msg = message(conv.id)
        precheck_db = FakeSession([msg, conv])
        send = AsyncMock()
        add_to_stream = AsyncMock()
        redis = self._redis()

        with (
            patch.object(
                outgoing_worker,
                "make_tenant_session",
                SessionFactory(FakeSession([msg]), precheck_db),
            ),
            patch.object(outgoing_worker, "send_text_message", send),
            patch.object(outgoing_worker, "xadd", add_to_stream),
        ):
            completed = await outgoing_worker._process_entry(redis, "1-0", handoff_data(conv, msg))

        self.assertTrue(completed)
        send.assert_not_awaited()
        add_to_stream.assert_not_awaited()
        self.assertEqual(conv.status, ConversationStatus.BOT_ACTIVE)
        self.assertEqual(precheck_db.commits, 1)

    async def test_processed_redelivery_is_fully_idempotent(self):
        conv = conversation(status=ConversationStatus.WAITING_HUMAN)
        msg = message(conv.id, status=MessageStatus.PROCESSED)
        status_db = FakeSession([msg])
        send = AsyncMock()
        add_to_stream = AsyncMock()
        publish = AsyncMock()
        redis = self._redis()

        with (
            patch.object(
                outgoing_worker,
                "make_tenant_session",
                SessionFactory(FakeSession([msg]), status_db),
            ),
            patch.object(outgoing_worker, "send_text_message", send),
            patch.object(outgoing_worker, "xadd", add_to_stream),
            patch.object(outgoing_worker.manager, "publish", publish),
        ):
            completed = await outgoing_worker._process_entry(redis, "1-0", handoff_data(conv, msg))

        self.assertTrue(completed)
        send.assert_not_awaited()
        add_to_stream.assert_not_awaited()
        publish.assert_not_awaited()

    async def test_exhausted_error_redelivery_is_fully_idempotent(self):
        conv = conversation(status=ConversationStatus.BOT_ACTIVE)
        msg = message(conv.id, status=MessageStatus.ERROR)
        status_db = FakeSession([msg])
        send = AsyncMock()
        add_to_stream = AsyncMock()
        redis = self._redis()

        with (
            patch.object(
                outgoing_worker,
                "make_tenant_session",
                SessionFactory(FakeSession([msg]), status_db),
            ),
            patch.object(outgoing_worker, "send_text_message", send),
            patch.object(outgoing_worker, "xadd", add_to_stream),
        ):
            completed = await outgoing_worker._process_entry(
                redis, "1-0", handoff_data(conv, msg)
            )

        self.assertTrue(completed)
        send.assert_not_awaited()
        add_to_stream.assert_not_awaited()

    async def test_concurrent_worker_cannot_send_same_message(self):
        conv = conversation()
        msg = message(conv.id)
        redis = self._redis()
        redis.set.return_value = False
        send = AsyncMock()

        with patch.object(outgoing_worker, "send_text_message", send):
            completed = await outgoing_worker._process_entry(
                redis, "1-0", handoff_data(conv, msg)
            )

        self.assertFalse(completed)
        send.assert_not_awaited()
        redis.eval.assert_not_awaited()

    async def test_bot_output_waits_while_conversation_action_is_locked(self):
        conv = conversation()
        msg = message(conv.id, sender_type=SenderType.BOT)
        redis = self._redis()
        redis.set.side_effect = [True, False]
        send = AsyncMock()

        with (
            patch.object(
                outgoing_worker,
                "make_tenant_session",
                SessionFactory(FakeSession([msg])),
            ),
            patch.object(outgoing_worker, "send_text_message", send),
        ):
            completed = await outgoing_worker._process_entry(
                redis, "1-0", handoff_data(conv, msg)
            )

        self.assertFalse(completed)
        send.assert_not_awaited()
        redis.eval.assert_awaited_once()

    async def test_queued_bot_reply_is_cancelled_after_agent_takeover(self):
        conv = conversation(status=ConversationStatus.HUMAN_ACTIVE)
        msg = message(conv.id, sender_type=SenderType.BOT)
        precheck_db = FakeSession([msg, conv])
        send = AsyncMock()
        redis = self._redis()

        data = handoff_data(conv, msg)
        data["handoff_after_send"] = False
        data.pop("conversation_id")
        with (
            patch.object(
                outgoing_worker,
                "make_tenant_session",
                SessionFactory(FakeSession([msg]), precheck_db),
            ),
            patch.object(outgoing_worker, "send_text_message", send),
        ):
            completed = await outgoing_worker._process_entry(redis, "1-0", data)

        self.assertTrue(completed)
        send.assert_not_awaited()
        self.assertEqual(precheck_db.commits, 1)

    async def test_queued_human_text_uses_template_if_window_expires(self):
        conv = conversation(
            status=ConversationStatus.HUMAN_ACTIVE,
            last_user_message_at=datetime.now(timezone.utc) - timedelta(hours=25),
        )
        msg = message(conv.id, sender_type=SenderType.HUMAN)
        precheck_db = FakeSession([msg, conv])
        completion_db = FakeSession([msg])
        send_text = AsyncMock()
        send_template = AsyncMock()
        redis = self._redis()

        data = handoff_data(conv, msg)
        data.update({
            "handoff_after_send": False,
            "template_name": "reabrir_chat",
            "template_language": "es",
        })
        with (
            patch.object(
                outgoing_worker,
                "make_tenant_session",
                SessionFactory(FakeSession([msg]), precheck_db, completion_db),
            ),
            patch.object(outgoing_worker, "send_text_message", send_text),
            patch.object(outgoing_worker, "send_template_message", send_template),
        ):
            completed = await outgoing_worker._process_entry(redis, "1-0", data)

        self.assertTrue(completed)
        send_text.assert_not_awaited()
        send_template.assert_awaited_once()


class AssignmentSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_waiting_conversation_outside_window_is_not_notified(self):
        conv = conversation(
            status=ConversationStatus.WAITING_HUMAN,
            last_user_message_at=datetime.now(timezone.utc) - timedelta(hours=25),
        )
        send = AsyncMock()

        with patch.object(assignment_worker, "send_text_message", send):
            allowed = await assignment_worker._ensure_handoff_notice(
                FakeSession(), conv.tenant_id, "prueba", conv
            )

        self.assertFalse(allowed)
        send.assert_not_awaited()
        self.assertIsNone(conv.handoff_notice_sent_at)

    async def test_meta_failure_keeps_legacy_waiting_conversation_unnotified(self):
        conv = conversation(status=ConversationStatus.WAITING_HUMAN)
        public_db = FakeSession([tenant(id=conv.tenant_id)])
        send = AsyncMock(side_effect=RuntimeError("Meta unavailable"))

        with (
            patch.object(
                assignment_worker,
                "AsyncSessionLocal",
                SessionFactory(public_db),
            ),
            patch.object(assignment_worker, "send_text_message", send),
        ):
            allowed = await assignment_worker._ensure_handoff_notice(
                FakeSession(), conv.tenant_id, "prueba", conv
            )

        self.assertFalse(allowed)
        self.assertIsNone(conv.handoff_notice_sent_at)

    async def test_no_available_agent_acks_and_relies_on_rescue_scanner(self):
        conv = conversation(
            status=ConversationStatus.WAITING_HUMAN,
            handoff_notice_sent_at=datetime.now(timezone.utc),
        )
        db = FakeSession([conv, conv])
        assign = AsyncMock(return_value=None)
        redis = SimpleNamespace(
            set=AsyncMock(return_value=True),
            eval=AsyncMock(return_value=1),
        )

        with (
            patch.object(
                assignment_worker,
                "make_tenant_session",
                SessionFactory(db),
            ),
            patch.object(assignment_worker, "assign_agent", assign),
        ):
            completed = await assignment_worker._process_entry(
                redis,
                "1-0",
                {
                    "tenant_id": str(conv.tenant_id),
                    "tenant_slug": "prueba",
                    "conversation_id": str(conv.id),
                    "phone": conv.phone,
                },
            )

        self.assertTrue(completed)
        assign.assert_awaited_once()
        redis.eval.assert_awaited_once()

    async def test_concurrent_handoff_flow_does_not_notify_or_assign(self):
        conv = conversation(status=ConversationStatus.WAITING_HUMAN)
        redis = SimpleNamespace(
            set=AsyncMock(return_value=False),
            eval=AsyncMock(),
        )
        send = AsyncMock()
        assign = AsyncMock()

        with (
            patch.object(assignment_worker, "send_text_message", send),
            patch.object(assignment_worker, "assign_agent", assign),
        ):
            completed = await assignment_worker._process_entry(
                redis,
                "1-0",
                {
                    "tenant_id": str(conv.tenant_id),
                    "tenant_slug": "prueba",
                    "conversation_id": str(conv.id),
                    "phone": conv.phone,
                },
            )

        self.assertFalse(completed)
        send.assert_not_awaited()
        assign.assert_not_awaited()
        redis.eval.assert_not_awaited()


class ManualCloseTests(unittest.IsolatedAsyncioTestCase):
    def _tenant_context(self, conv):
        return SimpleNamespace(
            id=conv.tenant_id,
            slug="prueba",
            whatsapp_phone_id="phone-id",
            whatsapp_token="token",
        )

    async def test_manual_close_notifies_before_commit(self):
        conv = conversation(status=ConversationStatus.HUMAN_ACTIVE)
        db = FakeSession([conv])
        send = AsyncMock()
        publish = AsyncMock()

        with (
            patch.object(conversations_api, "send_text_message", send),
            patch.object(conversations_api.manager, "publish", publish),
        ):
            await conversations_api._close_conversation_locked(
                conv.id,
                tenant=self._tenant_context(conv),
                db=db,
                agent=SimpleNamespace(id=uuid.uuid4()),
            )

        send.assert_awaited_once()
        self.assertEqual(db.commits, 1)
        self.assertEqual(len(db.added), 1)
        self.assertEqual(len(db.executed), 2)
        self.assertEqual(publish.await_count, 2)

    async def test_manual_close_meta_failure_does_not_commit(self):
        conv = conversation(status=ConversationStatus.HUMAN_ACTIVE)
        db = FakeSession([conv])
        send = AsyncMock(side_effect=RuntimeError("Meta unavailable"))

        with patch.object(conversations_api, "send_text_message", send):
            with self.assertRaises(HTTPException) as raised:
                await conversations_api._close_conversation_locked(
                    conv.id,
                    tenant=self._tenant_context(conv),
                    db=db,
                    agent=SimpleNamespace(id=uuid.uuid4()),
                )

        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(db.commits, 0)
        self.assertEqual(db.added, [])

    async def test_manual_close_outside_24h_is_rejected_not_silent(self):
        conv = conversation(
            status=ConversationStatus.HUMAN_ACTIVE,
            last_user_message_at=datetime.now(timezone.utc) - timedelta(hours=25),
        )
        db = FakeSession([conv])
        send = AsyncMock()

        with patch.object(conversations_api, "send_text_message", send):
            with self.assertRaises(HTTPException) as raised:
                await conversations_api._close_conversation_locked(
                    conv.id,
                    tenant=self._tenant_context(conv),
                    db=db,
                    agent=SimpleNamespace(id=uuid.uuid4()),
                )

        self.assertEqual(raised.exception.status_code, 409)
        send.assert_not_awaited()
        self.assertEqual(db.commits, 0)

    async def test_repeated_manual_close_does_not_send_duplicate_farewell(self):
        conv = conversation(status=ConversationStatus.CLOSED)
        db = FakeSession([conv])
        send = AsyncMock()

        with patch.object(conversations_api, "send_text_message", send):
            with self.assertRaises(HTTPException) as raised:
                await conversations_api._close_conversation_locked(
                    conv.id,
                    tenant=self._tenant_context(conv),
                    db=db,
                    agent=SimpleNamespace(id=uuid.uuid4()),
                )

        self.assertEqual(raised.exception.status_code, 409)
        send.assert_not_awaited()
        self.assertEqual(db.commits, 0)

    async def test_manual_close_is_rejected_while_conversation_is_locked(self):
        conv = conversation(status=ConversationStatus.HUMAN_ACTIVE)
        redis = SimpleNamespace(
            set=AsyncMock(return_value=False),
            eval=AsyncMock(),
        )

        with patch.object(
            conversations_api, "get_redis", AsyncMock(return_value=redis)
        ):
            with self.assertRaises(HTTPException) as raised:
                await conversations_api.close_conversation(
                    conv.id,
                    tenant=self._tenant_context(conv),
                    db=FakeSession(),
                    agent=SimpleNamespace(id=uuid.uuid4()),
                )

        self.assertEqual(raised.exception.status_code, 409)
        redis.eval.assert_not_awaited()

    async def test_manual_close_releases_lock_when_inner_operation_fails(self):
        conv = conversation(status=ConversationStatus.HUMAN_ACTIVE)
        redis = SimpleNamespace(
            set=AsyncMock(return_value=True),
            eval=AsyncMock(return_value=1),
        )

        with (
            patch.object(conversations_api, "get_redis", AsyncMock(return_value=redis)),
            patch.object(
                conversations_api,
                "_close_conversation_locked",
                AsyncMock(side_effect=RuntimeError("db failed")),
            ),
        ):
            with self.assertRaises(RuntimeError):
                await conversations_api.close_conversation(
                    conv.id,
                    tenant=self._tenant_context(conv),
                    db=FakeSession(),
                    agent=SimpleNamespace(id=uuid.uuid4()),
                )

        redis.eval.assert_awaited_once()


class AgentOutgoingQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_enqueue_does_not_change_message_status(self):
        db = FakeSession()
        redis = object()
        add_to_stream = AsyncMock()

        with patch.object(conversations_api, "xadd", add_to_stream):
            await conversations_api._publish_outgoing_or_fail(
                db,
                redis,
                uuid.uuid4(),
                {"content": "hola"},
            )

        add_to_stream.assert_awaited_once()
        self.assertEqual(db.executed, [])
        self.assertEqual(db.commits, 0)

    async def test_enqueue_failure_marks_error_and_returns_503(self):
        db = FakeSession()
        message_id = uuid.uuid4()
        add_to_stream = AsyncMock(side_effect=RuntimeError("Redis unavailable"))

        with patch.object(conversations_api, "xadd", add_to_stream):
            with self.assertRaises(HTTPException) as raised:
                await conversations_api._publish_outgoing_or_fail(
                    db,
                    object(),
                    message_id,
                    {"content": "hola"},
                )

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(db.commits, 1)
        status_updates = [
            args[0].compile().params.get("status")
            for args, _ in db.executed
            if args and hasattr(args[0], "compile")
        ]
        self.assertIn(MessageStatus.ERROR, status_updates)


class StartConversationConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    def _tenant_context(self):
        return SimpleNamespace(
            id=uuid.uuid4(),
            slug="prueba",
            whatsapp_phone_id="phone-id",
            whatsapp_token="token",
            whatsapp_template_name="inicio_chat",
            whatsapp_template_language="es",
        )

    async def test_phone_advisory_lock_precedes_open_conversation_check(self):
        tenant_context = self._tenant_context()
        existing = conversation(
            tenant_id=tenant_context.id,
            status=ConversationStatus.HUMAN_ACTIVE,
        )
        db = FakeSession([existing])

        with self.assertRaises(HTTPException) as raised:
            await conversations_api.start_conversation(
                conversations_api.StartConversationBody(phone=existing.phone),
                tenant=tenant_context,
                db=db,
                agent=SimpleNamespace(id=uuid.uuid4()),
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(len(db.executed), 1)
        self.assertIn("pg_advisory_xact_lock", str(db.executed[0][0][0]))

    async def test_reopen_cas_failure_rolls_back_without_assignment(self):
        tenant_context = self._tenant_context()
        closed = conversation(
            tenant_id=tenant_context.id,
            status=ConversationStatus.CLOSED,
            last_user_message_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db = FakeSession(
            [None, closed],
            execute_results=[
                SimpleNamespace(),
                SimpleNamespace(rowcount=0),
            ],
        )
        send = AsyncMock()

        with patch.object(conversations_api, "send_text_message", send):
            with self.assertRaises(HTTPException) as raised:
                await conversations_api.start_conversation(
                    conversations_api.StartConversationBody(phone=closed.phone),
                    tenant=tenant_context,
                    db=db,
                    agent=SimpleNamespace(id=uuid.uuid4()),
                )

        self.assertEqual(raised.exception.status_code, 409)
        send.assert_awaited_once()
        self.assertEqual(db.rollbacks, 1)
        self.assertEqual(db.added, [])


class ManualTakeLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_take_is_rejected_while_handoff_flow_is_locked(self):
        conv = conversation(status=ConversationStatus.BOT_ACTIVE)
        redis = SimpleNamespace(
            set=AsyncMock(return_value=False),
            eval=AsyncMock(),
        )
        db = FakeSession()
        send = AsyncMock()

        with (
            patch.object(conversations_api, "get_redis", AsyncMock(return_value=redis)),
            patch.object(conversations_api, "send_text_message", send),
        ):
            with self.assertRaises(HTTPException) as raised:
                await conversations_api.take_conversation(
                    conv.id,
                    tenant=SimpleNamespace(id=conv.tenant_id, slug="prueba"),
                    db=db,
                    agent=SimpleNamespace(id=uuid.uuid4()),
                )

        self.assertEqual(raised.exception.status_code, 409)
        send.assert_not_awaited()
        self.assertEqual(db.commits, 0)
        redis.eval.assert_not_awaited()

    async def test_manual_take_rejects_pending_bot_output(self):
        conv = conversation(status=ConversationStatus.BOT_ACTIVE)
        db = FakeSession([conv, uuid.uuid4()])
        send = AsyncMock()

        with patch.object(conversations_api, "send_text_message", send):
            with self.assertRaises(HTTPException) as raised:
                await conversations_api._take_conversation_locked(
                    conv.id,
                    tenant=SimpleNamespace(
                        id=conv.tenant_id,
                        slug="prueba",
                        whatsapp_phone_id="phone-id",
                        whatsapp_token="token",
                    ),
                    db=db,
                    agent=SimpleNamespace(id=uuid.uuid4()),
                )

        self.assertEqual(raised.exception.status_code, 409)
        send.assert_not_awaited()
        self.assertEqual(db.commits, 0)

    async def test_manual_take_releases_lock_when_inner_operation_fails(self):
        conv = conversation(status=ConversationStatus.BOT_ACTIVE)
        redis = SimpleNamespace(
            set=AsyncMock(return_value=True),
            eval=AsyncMock(return_value=1),
        )

        with (
            patch.object(conversations_api, "get_redis", AsyncMock(return_value=redis)),
            patch.object(
                conversations_api,
                "_take_conversation_locked",
                AsyncMock(side_effect=RuntimeError("db failed")),
            ),
        ):
            with self.assertRaises(RuntimeError):
                await conversations_api.take_conversation(
                    conv.id,
                    tenant=SimpleNamespace(id=conv.tenant_id, slug="prueba"),
                    db=FakeSession(),
                    agent=SimpleNamespace(id=uuid.uuid4()),
                )

        redis.eval.assert_awaited_once()


class FakeExecuteResult:
    def __init__(self, *, scalar=None, rowcount=None):
        self._scalar = scalar
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar


class RoundRobinDb:
    def __init__(self, *results):
        self.results = iter(results)
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, *args, **kwargs):
        try:
            return next(self.results)
        except StopIteration as exc:
            raise AssertionError("Unexpected round-robin db.execute()") from exc

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class RoundRobinConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    def _redis(self, agent_id):
        return SimpleNamespace(
            set=AsyncMock(return_value=True),
            llen=AsyncMock(return_value=1),
            rpoplpush=AsyncMock(return_value=str(agent_id)),
            delete=AsyncMock(),
        )

    async def test_status_change_prevents_duplicate_assignment(self):
        agent = SimpleNamespace(id=uuid.uuid4(), max_concurrent_chats=5)
        db = RoundRobinDb(
            FakeExecuteResult(scalar=agent),
            FakeExecuteResult(scalar=0),
            FakeExecuteResult(rowcount=0),
        )
        redis = self._redis(agent.id)

        with patch.object(round_robin, "is_online", AsyncMock(return_value=True)):
            result = await round_robin.assign_agent(
                redis, db, "prueba", uuid.uuid4()
            )

        self.assertIsNone(result)
        self.assertEqual(db.added, [])
        self.assertEqual(db.commits, 0)
        self.assertEqual(db.rollbacks, 1)

    async def test_valid_waiting_transition_creates_one_assignment(self):
        agent = SimpleNamespace(id=uuid.uuid4(), max_concurrent_chats=5)
        db = RoundRobinDb(
            FakeExecuteResult(scalar=agent),
            FakeExecuteResult(scalar=0),
            FakeExecuteResult(rowcount=1),
            FakeExecuteResult(rowcount=1),
        )
        redis = self._redis(agent.id)

        with patch.object(round_robin, "is_online", AsyncMock(return_value=True)):
            result = await round_robin.assign_agent(
                redis, db, "prueba", uuid.uuid4()
            )

        self.assertEqual(result, agent)
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.commits, 1)
        self.assertEqual(db.rollbacks, 0)


class InactivityLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifecycle_waits_when_conversation_action_is_locked(self):
        redis = SimpleNamespace(set=AsyncMock(return_value=False), eval=AsyncMock())
        operation = AsyncMock()

        completed = await conversation_lifecycle._run_with_conversation_lock(
            redis, uuid.uuid4(), operation
        )

        self.assertFalse(completed)
        operation.assert_not_awaited()
        redis.eval.assert_not_awaited()

    async def test_warning_is_saved_only_after_meta_success(self):
        now = datetime.now(timezone.utc)
        conv = conversation(
            last_user_message_at=now - timedelta(hours=2),
            last_activity_at=now - timedelta(minutes=40),
        )
        latest = message(
            conv.id,
            sender_type=SenderType.BOT,
            status=MessageStatus.PROCESSED,
            created_at=conv.last_activity_at,
        )
        db = FakeSession([conv, latest])
        send = AsyncMock()
        publish = AsyncMock()

        with (
            patch.object(
                conversation_lifecycle,
                "make_tenant_session",
                SessionFactory(db),
            ),
            patch.object(conversation_lifecycle, "send_text_message", send),
            patch.object(conversation_lifecycle.manager, "publish", publish),
        ):
            await conversation_lifecycle._warn_conversation(
                tenant(), conv.id, now - timedelta(minutes=30)
            )

        send.assert_awaited_once()
        self.assertIsNotNone(conv.idle_warning_sent_at)
        self.assertEqual(db.commits, 1)
        self.assertEqual(len(db.added), 1)
        publish.assert_awaited_once()

    async def test_warning_meta_failure_does_not_start_grace(self):
        now = datetime.now(timezone.utc)
        conv = conversation(
            last_user_message_at=now - timedelta(hours=2),
            last_activity_at=now - timedelta(minutes=40),
        )
        latest = message(
            conv.id,
            sender_type=SenderType.BOT,
            status=MessageStatus.PROCESSED,
            created_at=conv.last_activity_at,
        )
        db = FakeSession([conv, latest])
        send = AsyncMock(side_effect=RuntimeError("Meta unavailable"))

        with (
            patch.object(
                conversation_lifecycle,
                "make_tenant_session",
                SessionFactory(db),
            ),
            patch.object(conversation_lifecycle, "send_text_message", send),
        ):
            with self.assertRaises(RuntimeError):
                await conversation_lifecycle._warn_conversation(
                    tenant(), conv.id, now - timedelta(minutes=30)
                )

        self.assertIsNone(conv.idle_warning_sent_at)
        self.assertEqual(db.commits, 0)
        self.assertEqual(db.added, [])

    async def test_close_is_cancelled_when_new_message_exists_after_warning(self):
        now = datetime.now(timezone.utc)
        warning_at = now - timedelta(minutes=15)
        conv = conversation(
            idle_warning_sent_at=warning_at,
            last_user_message_at=now - timedelta(hours=2),
        )
        latest = message(
            conv.id,
            sender_type=SenderType.USER,
            status=MessageStatus.PENDING,
            created_at=warning_at + timedelta(minutes=1),
        )
        db = FakeSession([conv, latest])
        send = AsyncMock()

        with (
            patch.object(
                conversation_lifecycle,
                "make_tenant_session",
                SessionFactory(db),
            ),
            patch.object(conversation_lifecycle, "send_text_message", send),
        ):
            await conversation_lifecycle._close_conversation(
                tenant(), conv.id, now - timedelta(minutes=10)
            )

        send.assert_not_awaited()
        self.assertEqual(conv.status, ConversationStatus.BOT_ACTIVE)
        self.assertEqual(db.commits, 0)

    async def test_close_changes_status_only_after_meta_success(self):
        now = datetime.now(timezone.utc)
        warning_at = now - timedelta(minutes=15)
        conv = conversation(
            idle_warning_sent_at=warning_at,
            last_user_message_at=now - timedelta(hours=2),
        )
        latest = message(
            conv.id,
            sender_type=SenderType.BOT,
            status=MessageStatus.PROCESSED,
            created_at=warning_at,
        )
        db = FakeSession([conv, latest])
        send = AsyncMock()
        publish = AsyncMock()

        with (
            patch.object(
                conversation_lifecycle,
                "make_tenant_session",
                SessionFactory(db),
            ),
            patch.object(conversation_lifecycle, "send_text_message", send),
            patch.object(conversation_lifecycle.manager, "publish", publish),
        ):
            await conversation_lifecycle._close_conversation(
                tenant(), conv.id, now - timedelta(minutes=10)
            )

        send.assert_awaited_once()
        self.assertEqual(conv.status, ConversationStatus.CLOSED)
        self.assertIsNotNone(conv.closed_at)
        self.assertEqual(db.commits, 1)
        self.assertEqual(publish.await_count, 2)

    async def test_close_meta_failure_leaves_conversation_open(self):
        now = datetime.now(timezone.utc)
        warning_at = now - timedelta(minutes=15)
        conv = conversation(
            idle_warning_sent_at=warning_at,
            last_user_message_at=now - timedelta(hours=2),
        )
        latest = message(
            conv.id,
            sender_type=SenderType.BOT,
            status=MessageStatus.PROCESSED,
            created_at=warning_at,
        )
        db = FakeSession([conv, latest])
        send = AsyncMock(side_effect=RuntimeError("Meta unavailable"))

        with (
            patch.object(
                conversation_lifecycle,
                "make_tenant_session",
                SessionFactory(db),
            ),
            patch.object(conversation_lifecycle, "send_text_message", send),
        ):
            with self.assertRaises(RuntimeError):
                await conversation_lifecycle._close_conversation(
                    tenant(), conv.id, now - timedelta(minutes=10)
                )

        self.assertEqual(conv.status, ConversationStatus.BOT_ACTIVE)
        self.assertIsNone(conv.closed_at)
        self.assertEqual(db.commits, 0)

    async def test_waiting_human_timeout_notifies_then_closes(self):
        now = datetime.now(timezone.utc)
        conv = conversation(
            status=ConversationStatus.WAITING_HUMAN,
            handoff_notice_sent_at=now - timedelta(minutes=70),
            last_activity_at=now - timedelta(minutes=70),
            last_user_message_at=now - timedelta(hours=2),
        )
        db = FakeSession([conv])
        send = AsyncMock()
        publish = AsyncMock()

        with (
            patch.object(
                conversation_lifecycle,
                "make_tenant_session",
                SessionFactory(db),
            ),
            patch.object(conversation_lifecycle, "send_text_message", send),
            patch.object(conversation_lifecycle.manager, "publish", publish),
        ):
            await conversation_lifecycle._close_waiting_conversation(
                tenant(),
                conv.id,
                now - timedelta(minutes=60),
                now - timedelta(hours=23, minutes=55),
            )

        send.assert_awaited_once()
        self.assertEqual(conv.status, ConversationStatus.CLOSED)
        self.assertIsNotNone(conv.closed_at)
        self.assertEqual(db.commits, 1)
        self.assertEqual(publish.await_count, 2)

    async def test_waiting_human_recent_activity_stays_open(self):
        now = datetime.now(timezone.utc)
        conv = conversation(
            status=ConversationStatus.WAITING_HUMAN,
            handoff_notice_sent_at=now - timedelta(minutes=10),
            last_activity_at=now - timedelta(minutes=10),
            last_user_message_at=now - timedelta(hours=2),
        )
        db = FakeSession([conv])
        send = AsyncMock()

        with (
            patch.object(
                conversation_lifecycle,
                "make_tenant_session",
                SessionFactory(db),
            ),
            patch.object(conversation_lifecycle, "send_text_message", send),
        ):
            await conversation_lifecycle._close_waiting_conversation(
                tenant(),
                conv.id,
                now - timedelta(minutes=60),
                now - timedelta(hours=23, minutes=55),
            )

        send.assert_not_awaited()
        self.assertEqual(conv.status, ConversationStatus.WAITING_HUMAN)

    async def test_waiting_human_outside_24h_does_not_send_free_text(self):
        now = datetime.now(timezone.utc)
        conv = conversation(
            status=ConversationStatus.WAITING_HUMAN,
            handoff_notice_sent_at=now - timedelta(hours=25),
            last_activity_at=now - timedelta(hours=25),
            last_user_message_at=now - timedelta(hours=25),
        )
        db = FakeSession([conv])
        send = AsyncMock()

        with (
            patch.object(
                conversation_lifecycle,
                "make_tenant_session",
                SessionFactory(db),
            ),
            patch.object(conversation_lifecycle, "send_text_message", send),
        ):
            await conversation_lifecycle._close_waiting_conversation(
                tenant(),
                conv.id,
                now - timedelta(minutes=60),
                now - timedelta(hours=23, minutes=55),
            )

        send.assert_not_awaited()
        self.assertEqual(conv.status, ConversationStatus.WAITING_HUMAN)

    async def test_waiting_human_meta_failure_does_not_close(self):
        now = datetime.now(timezone.utc)
        conv = conversation(
            status=ConversationStatus.WAITING_HUMAN,
            handoff_notice_sent_at=now - timedelta(minutes=70),
            last_activity_at=now - timedelta(minutes=70),
            last_user_message_at=now - timedelta(hours=2),
        )
        db = FakeSession([conv])
        send = AsyncMock(side_effect=RuntimeError("Meta unavailable"))

        with (
            patch.object(
                conversation_lifecycle,
                "make_tenant_session",
                SessionFactory(db),
            ),
            patch.object(conversation_lifecycle, "send_text_message", send),
        ):
            with self.assertRaises(RuntimeError):
                await conversation_lifecycle._close_waiting_conversation(
                    tenant(),
                    conv.id,
                    now - timedelta(minutes=60),
                    now - timedelta(hours=23, minutes=55),
                )

        self.assertEqual(conv.status, ConversationStatus.WAITING_HUMAN)
        self.assertIsNone(conv.closed_at)
        self.assertEqual(db.commits, 0)

    async def test_expired_window_cleanup_closes_and_releases_without_sending(self):
        now = datetime.now(timezone.utc)
        conv = conversation(
            status=ConversationStatus.WAITING_HUMAN,
            assigned_agent_id=uuid.uuid4(),
            last_user_message_at=now - timedelta(hours=25),
            last_activity_at=now - timedelta(hours=2),
        )
        db = FakeSession([conv])
        publish = AsyncMock()

        with (
            patch.object(
                conversation_lifecycle,
                "make_tenant_session",
                SessionFactory(db),
            ),
            patch.object(conversation_lifecycle.manager, "publish", publish),
        ):
            await conversation_lifecycle._close_expired_conversation(
                "prueba", conv.id, now - timedelta(minutes=60)
            )

        self.assertEqual(conv.status, ConversationStatus.CLOSED)
        self.assertIsNone(conv.assigned_agent_id)
        self.assertIsNotNone(conv.closed_at)
        self.assertEqual(db.commits, 1)
        self.assertEqual(len(db.executed), 1)
        publish.assert_awaited_once()

    async def test_expired_window_cleanup_preserves_recent_activity(self):
        now = datetime.now(timezone.utc)
        conv = conversation(
            status=ConversationStatus.HUMAN_ACTIVE,
            last_user_message_at=now - timedelta(hours=25),
            last_activity_at=now - timedelta(minutes=10),
        )
        db = FakeSession([conv])
        publish = AsyncMock()

        with (
            patch.object(
                conversation_lifecycle,
                "make_tenant_session",
                SessionFactory(db),
            ),
            patch.object(conversation_lifecycle.manager, "publish", publish),
        ):
            await conversation_lifecycle._close_expired_conversation(
                "prueba", conv.id, now - timedelta(minutes=60)
            )

        self.assertEqual(conv.status, ConversationStatus.HUMAN_ACTIVE)
        self.assertEqual(db.commits, 0)
        publish.assert_not_awaited()

    async def test_expired_cleanup_never_closes_open_24h_window(self):
        now = datetime.now(timezone.utc)
        conv = conversation(
            status=ConversationStatus.BOT_ACTIVE,
            last_user_message_at=now - timedelta(hours=23),
            last_activity_at=now - timedelta(hours=2),
        )
        db = FakeSession([conv])

        with patch.object(
            conversation_lifecycle,
            "make_tenant_session",
            SessionFactory(db),
        ):
            await conversation_lifecycle._close_expired_conversation(
                "prueba", conv.id, now - timedelta(minutes=60)
            )

        self.assertEqual(conv.status, ConversationStatus.BOT_ACTIVE)
        self.assertEqual(db.commits, 0)


if __name__ == "__main__":
    unittest.main()
