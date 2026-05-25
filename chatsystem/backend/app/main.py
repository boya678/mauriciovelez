"""
ChatsSystem — FastAPI application entry point.

Lifespan:
  startup  → start Redis, verify DB connection, launch workers
  shutdown → stop workers, close Redis
"""
import logging
import traceback
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.webhook import router as webhook_router
from app.api.conversations import router as conversations_router
from app.api.agents import router as agents_router
from app.api.ws import router as ws_router
from app.api.tenants import router as tenants_router
from app.api.tools import router as tools_router
from app.api.superadmin import router as superadmin_router
from app.api.knowledge import router as knowledge_router
from app.api.token_usage import router as token_usage_router
from app.api.message_stats import router as message_stats_router
from app.redis.client import init_redis, close_redis
from app.workers.runner import start_workers, stop_workers
from app.websocket.manager import manager
from app.services.tenant_cache import start_invalidation_listener
import asyncio

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
# Make sure uvicorn loggers propagate to root so we see everything
for _uvicorn_logger in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(_uvicorn_logger).propagate = True
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup
    logger.info("Starting ChatsSystem backend…")

    redis = await init_redis()
    manager.set_redis(redis)

    invalidation_task = start_invalidation_listener(redis)

    worker_tasks = await start_workers()
    logger.info("All workers running")

    yield

    # Shutdown
    logger.info("Shutting down…")
    invalidation_task.cancel()
    try:
        await invalidation_task
    except asyncio.CancelledError:
        pass
    await stop_workers(worker_tasks)
    await close_redis()
    logger.info("Shutdown complete")


app = FastAPI(
    title="ChatsSystem API",
    version="1.0.0",
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None,
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global exception handler (logs 500s before they go silent) ────────────────

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception on %s %s\n%s",
        request.method,
        request.url.path,
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(webhook_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(tools_router, prefix="/api/v1")
app.include_router(superadmin_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(token_usage_router, prefix="/api/v1")
app.include_router(message_stats_router, prefix="/api/v1")
app.include_router(ws_router)  # WebSocket has its own path prefix


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
