import asyncio
import json
import signal
import unittest
from unittest.mock import patch

from app.workers import runner


class WorkerSupervisionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        if runner._stop_event is not None:
            runner._stop_event.set()
        for task in list(runner._worker_tasks):
            if not task.done():
                task.cancel()
        if runner._worker_tasks:
            await asyncio.gather(*runner._worker_tasks, return_exceptions=True)
        runner._worker_tasks = []
        runner._stop_event = None

    async def test_health_snapshot_reports_all_running_tasks(self):
        blocker = asyncio.Event()
        tasks = [
            asyncio.create_task(blocker.wait(), name="worker:ai"),
            asyncio.create_task(blocker.wait(), name="worker:outgoing"),
        ]
        runner._worker_tasks = tasks
        runner._stop_event = asyncio.Event()

        snapshot = runner.worker_health_snapshot()

        self.assertTrue(snapshot["healthy"])
        self.assertEqual(snapshot["workers"]["worker:ai"], "running")
        self.assertEqual(snapshot["workers"]["worker:outgoing"], "running")

    async def test_unexpected_worker_completion_signals_process(self):
        async def finishes():
            return None

        runner._stop_event = asyncio.Event()
        task = asyncio.create_task(finishes(), name="worker:ai")
        await task
        runner._worker_tasks = [task]

        with patch.object(runner.os, "kill") as kill:
            runner._on_worker_done(task)

        kill.assert_called_once_with(runner.os.getpid(), signal.SIGTERM)
        self.assertFalse(runner.worker_health_snapshot()["healthy"])

    async def test_shutdown_completion_does_not_signal_process(self):
        async def finishes():
            return None

        runner._stop_event = asyncio.Event()
        runner._stop_event.set()
        task = asyncio.create_task(finishes(), name="worker:ai")
        await task
        runner._worker_tasks = [task]

        with patch.object(runner.os, "kill") as kill:
            runner._on_worker_done(task)

        kill.assert_not_called()

    async def test_health_server_returns_503_for_dead_worker(self):
        async def finishes():
            return None

        task = asyncio.create_task(finishes(), name="worker:ai")
        await task
        runner._worker_tasks = [task]
        runner._stop_event = asyncio.Event()
        server = await runner.start_worker_health_server("127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()
        finally:
            server.close()
            await server.wait_closed()

        head, raw_body = response.split(b"\r\n\r\n", 1)
        body = json.loads(raw_body)
        self.assertIn(b"503 Service Unavailable", head)
        self.assertFalse(body["healthy"])
        self.assertEqual(body["workers"]["worker:ai"], "stopped")

    async def test_health_server_returns_200_when_all_workers_run(self):
        blocker = asyncio.Event()
        task = asyncio.create_task(blocker.wait(), name="worker:ai")
        runner._worker_tasks = [task]
        runner._stop_event = asyncio.Event()
        server = await runner.start_worker_health_server("127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()
        finally:
            server.close()
            await server.wait_closed()

        head, raw_body = response.split(b"\r\n\r\n", 1)
        body = json.loads(raw_body)
        self.assertIn(b"200 OK", head)
        self.assertTrue(body["healthy"])
        self.assertEqual(body["workers"]["worker:ai"], "running")

    async def test_start_workers_wires_supervisor_callback(self):
        async def wait_for_shutdown(stop_event):
            await stop_event.wait()

        async def stop_unexpectedly(stop_event):
            return None

        with (
            patch.object(runner, "run_ingestion", wait_for_shutdown),
            patch.object(runner, "run_ai", stop_unexpectedly),
            patch.object(runner, "run_assignment", wait_for_shutdown),
            patch.object(runner, "run_outgoing", wait_for_shutdown),
            patch.object(runner, "run_conversation_lifecycle", wait_for_shutdown),
            patch.object(runner.os, "kill") as kill,
        ):
            tasks = await runner.start_workers()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            runner._stop_event.set()
            await asyncio.gather(*tasks, return_exceptions=True)

        kill.assert_called_once_with(runner.os.getpid(), signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
