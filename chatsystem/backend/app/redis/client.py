import redis.asyncio as aioredis

from app.core.config import settings

_redis: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    global _redis
    _redis = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    await _redis.ping()
    return _redis


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        return await init_redis()
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
