"""
Starts all 4 workers in parallel as asyncio tasks.
Used by main.py lifespan OR run standalone:

  python -m app.workers.runner
"""
import asyncio
import json
import logging
import os
import signal

from app.workers.message_ingestion import run as run_ingestion
from app.workers.ai_worker import run as run_ai
from app.workers.assignment_worker import run as run_assignment
from app.workers.outgoing_worker import run as run_outgoing
from app.workers.conversation_lifecycle import run as run_conversation_lifecycle
from app.core.config import settings

logger = logging.getLogger(__name__)

_stop_event: asyncio.Event | None = None
_worker_tasks: list[asyncio.Task] = []


def worker_health_snapshot() -> dict:
    workers: dict[str, str] = {}
    for task in _worker_tasks:
        if task.cancelled():
            state = "cancelled"
        elif task.done():
            state = "failed" if task.exception() is not None else "stopped"
        else:
            state = "running"
        workers[task.get_name()] = state

    healthy = bool(workers) and all(state == "running" for state in workers.values())
    return {"healthy": healthy, "workers": workers}


def _on_worker_done(task: asyncio.Task) -> None:
    if _stop_event is not None and _stop_event.is_set():
        return

    if task.cancelled():
        logger.critical("Worker %s was cancelled unexpectedly", task.get_name())
    else:
        exc = task.exception()
        if exc is None:
            logger.critical("Worker %s stopped unexpectedly", task.get_name())
        else:
            logger.critical(
                "Worker %s crashed",
                task.get_name(),
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    # Uvicorn and the standalone runner handle SIGTERM gracefully. Kubernetes
    # then recreates the container because a critical internal worker vanished.
    os.kill(os.getpid(), signal.SIGTERM)


async def _handle_health_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        await asyncio.wait_for(reader.read(1024), timeout=2)
        snapshot = worker_health_snapshot()
        body = json.dumps(snapshot, separators=(",", ":")).encode("utf-8")
        status = "200 OK" if snapshot["healthy"] else "503 Service Unavailable"
        writer.write(
            (
                f"HTTP/1.1 {status}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii") + body
        )
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def start_worker_health_server(
    host: str = "0.0.0.0",
    port: int | None = None,
) -> asyncio.AbstractServer:
    server = await asyncio.start_server(
        _handle_health_request,
        host,
        settings.WORKER_HEALTH_PORT if port is None else port,
    )
    logger.info("Worker health server listening on %s:%s", host, server.sockets[0].getsockname()[1])
    return server


async def start_workers() -> list[asyncio.Task]:
    global _stop_event, _worker_tasks
    _stop_event = asyncio.Event()

    _worker_tasks = [
        asyncio.create_task(run_ingestion(_stop_event), name="worker:ingestion"),
        asyncio.create_task(run_ai(_stop_event), name="worker:ai"),
        asyncio.create_task(run_assignment(_stop_event), name="worker:assignment"),
        asyncio.create_task(run_outgoing(_stop_event), name="worker:outgoing"),
        asyncio.create_task(
            run_conversation_lifecycle(_stop_event),
            name="worker:conversation-lifecycle",
        ),
    ]
    for task in _worker_tasks:
        task.add_done_callback(_on_worker_done)
    logger.info("All workers started (%d tasks)", len(_worker_tasks))
    return _worker_tasks


async def stop_workers(tasks: list[asyncio.Task]) -> None:
    if _stop_event:
        _stop_event.set()
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("All workers stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    async def _main() -> None:
        stop = asyncio.Event()

        def _handle_signal() -> None:
            logger.info("Signal received, shutting down workers…")
            stop.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _handle_signal)

        tasks = await start_workers()
        health_server = await start_worker_health_server()
        try:
            await stop.wait()
        finally:
            await stop_workers(tasks)
            health_server.close()
            await health_server.wait_closed()

    asyncio.run(_main())
