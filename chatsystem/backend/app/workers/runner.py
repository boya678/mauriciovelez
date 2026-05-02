"""
Starts all 4 workers in parallel as asyncio tasks.
Used by main.py lifespan OR run standalone:

  python -m app.workers.runner
"""
import asyncio
import logging
import signal

from app.workers.message_ingestion import run as run_ingestion
from app.workers.ai_worker import run as run_ai
from app.workers.assignment_worker import run as run_assignment
from app.workers.outgoing_worker import run as run_outgoing

logger = logging.getLogger(__name__)

_stop_event: asyncio.Event | None = None


async def start_workers() -> list[asyncio.Task]:
    global _stop_event
    _stop_event = asyncio.Event()

    tasks = [
        asyncio.create_task(run_ingestion(_stop_event), name="worker:ingestion"),
        asyncio.create_task(run_ai(_stop_event), name="worker:ai"),
        asyncio.create_task(run_assignment(_stop_event), name="worker:assignment"),
        asyncio.create_task(run_outgoing(_stop_event), name="worker:outgoing"),
    ]
    logger.info("All workers started (%d tasks)", len(tasks))
    return tasks


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
        await stop.wait()
        await stop_workers(tasks)

    asyncio.run(_main())
