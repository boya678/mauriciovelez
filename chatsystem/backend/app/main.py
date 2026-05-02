"""
ChatsSystem — FastAPI application entry point.

Lifespan:
  startup  → start Redis, verify DB connection, launch workers
  shutdown → stop workers, close Redis
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.webhook import router as webhook_router
from app.api.conversations import router as conversations_router
from app.api.agents import router as agents_router
from app.api.ws import router as ws_router
from app.api.tenants import router as tenants_router
from app.api.tools import router as tools_router
from app.redis.client import init_redis, close_redis
from app.workers.runner import start_workers, stop_workers
from app.websocket.manager import manager

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup
    logger.info("Starting ChatsSystem backend…")
    redis = await init_redis()
    manager.set_redis(redis)

    worker_tasks = await start_workers()
    logger.info("All workers running")

    yield

    # Shutdown
    logger.info("Shutting down…")
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
    allow_origins=["*"],   # tighten in production via env var
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(webhook_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(tools_router, prefix="/api/v1")
app.include_router(ws_router)  # WebSocket has its own path prefix


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
