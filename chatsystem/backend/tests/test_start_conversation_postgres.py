import asyncio
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import conversations as conversations_api
from app.services.conversation_start_lock import acquire_conversation_start_lock


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")


@unittest.skipUnless(TEST_DATABASE_URL, "TEST_DATABASE_URL is not configured")
class StartConversationPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(TEST_DATABASE_URL, pool_size=5)
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
        )
        self.schema = "t_start_concurrency_test"
        self.tenant_id = uuid.uuid4()
        self.phone = "573001234567"
        self.closed_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        async with self.engine.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE"))
            await connection.execute(text(f"CREATE SCHEMA {self.schema}"))
            await connection.execute(text(
                f"""
                CREATE TABLE {self.schema}.conversations (
                    id UUID PRIMARY KEY,
                    tenant_id UUID NOT NULL,
                    phone VARCHAR(30) NOT NULL,
                    username VARCHAR(100),
                    bsuid VARCHAR(150),
                    status VARCHAR(30) NOT NULL,
                    assigned_agent_id UUID,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    closed_at TIMESTAMPTZ,
                    last_user_message_at TIMESTAMPTZ,
                    last_activity_at TIMESTAMPTZ,
                    idle_warning_sent_at TIMESTAMPTZ,
                    handoff_notice_sent_at TIMESTAMPTZ
                )
                """
            ))
            await connection.execute(text(
                f"""
                CREATE TABLE {self.schema}.messages (
                    id UUID PRIMARY KEY,
                    conversation_id UUID NOT NULL,
                    external_id VARCHAR(200) UNIQUE,
                    sender_type VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    message_type VARCHAR(30) NOT NULL DEFAULT 'text',
                    media_content TEXT,
                    media_mime_type VARCHAR(100),
                    imagen_descripcion TEXT,
                    status VARCHAR(20) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            ))
            await connection.execute(text(
                f"""
                CREATE TABLE {self.schema}.assignments (
                    id UUID PRIMARY KEY,
                    conversation_id UUID NOT NULL,
                    agent_id UUID NOT NULL,
                    assigned_at TIMESTAMPTZ NOT NULL,
                    released_at TIMESTAMPTZ
                )
                """
            ))
            await connection.execute(
                text(
                    f"""
                    INSERT INTO {self.schema}.conversations (
                        id, tenant_id, phone, status, created_at, updated_at,
                        closed_at, last_user_message_at, last_activity_at
                    ) VALUES (
                        :id, :tenant_id, :phone, 'closed', :created_at, :updated_at,
                        :closed_at, :last_user_message_at, :last_activity_at
                    )
                    """
                ),
                {
                    "id": self.closed_id,
                    "tenant_id": self.tenant_id,
                    "phone": self.phone,
                    "created_at": now - timedelta(hours=2),
                    "updated_at": now - timedelta(hours=1),
                    "closed_at": now - timedelta(hours=1),
                    "last_user_message_at": now - timedelta(hours=1),
                    "last_activity_at": now - timedelta(hours=1),
                },
            )

    async def asyncTearDown(self):
        async with self.engine.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA IF EXISTS {self.schema} CASCADE"))
        await self.engine.dispose()

    async def _start(self, agent_id):
        async with self.session_factory() as db:
            await db.execute(text(f"SET search_path TO {self.schema}, public"))
            try:
                return await conversations_api.start_conversation(
                    conversations_api.StartConversationBody(phone=self.phone),
                    tenant=SimpleNamespace(
                        id=self.tenant_id,
                        slug="start_concurrency_test",
                        whatsapp_phone_id="phone-id",
                        whatsapp_token="token",
                        whatsapp_template_name="inicio_chat",
                        whatsapp_template_language="es",
                    ),
                    db=db,
                    agent=SimpleNamespace(id=agent_id),
                )
            except HTTPException as exc:
                return exc

    async def test_concurrent_start_reopens_exactly_once(self):
        async def slow_meta_send(**kwargs):
            await asyncio.sleep(0.15)
            return {"messages": [{"id": "wamid.test"}]}

        send = AsyncMock(side_effect=slow_meta_send)
        publish = AsyncMock()
        agent_ids = [uuid.uuid4(), uuid.uuid4()]

        with (
            patch.object(conversations_api, "send_text_message", send),
            patch.object(conversations_api.manager, "publish", publish),
            patch.object(conversations_api, "record_messages", AsyncMock()),
            patch("app.db.session.AsyncSessionLocal", self.session_factory),
        ):
            results = await asyncio.gather(
                self._start(agent_ids[0]),
                self._start(agent_ids[1]),
            )

        successes = [result for result in results if not isinstance(result, HTTPException)]
        conflicts = [result for result in results if isinstance(result, HTTPException)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].status_code, 409)
        send.assert_awaited_once()

        async with self.session_factory() as db:
            await db.execute(text(f"SET search_path TO {self.schema}, public"))
            status = await db.scalar(text(
                "SELECT status FROM conversations WHERE id = :id"
            ), {"id": self.closed_id})
            messages = await db.scalar(text("SELECT COUNT(*) FROM messages"))
            assignments = await db.scalar(text("SELECT COUNT(*) FROM assignments"))

        self.assertEqual(status, "human_active")
        self.assertEqual(messages, 1)
        self.assertEqual(assignments, 1)

    async def test_inbound_transaction_blocks_outbound_start_lock(self):
        async with self.session_factory() as inbound_db, self.session_factory() as outbound_db:
            await acquire_conversation_start_lock(
                inbound_db, self.tenant_id, self.phone
            )

            outbound_waiter = asyncio.create_task(
                acquire_conversation_start_lock(
                    outbound_db, self.tenant_id, self.phone
                )
            )
            await asyncio.sleep(0.15)
            self.assertFalse(outbound_waiter.done())

            await inbound_db.commit()
            await asyncio.wait_for(outbound_waiter, timeout=1)
            await outbound_db.commit()


if __name__ == "__main__":
    unittest.main()
