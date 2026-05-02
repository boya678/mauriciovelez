from contextvars import ContextVar
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Context var to hold current tenant schema per request
_current_tenant_schema: ContextVar[str] = ContextVar("current_tenant_schema", default="public")


def set_tenant_schema(schema: str) -> None:
    _current_tenant_schema.set(schema)


def get_tenant_schema() -> str:
    return _current_tenant_schema.get()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        schema = get_tenant_schema()
        if schema and schema != "public":
            @event.listens_for(session.sync_session, "after_begin")
            def _set_search_path(sess, transaction, connection):
                connection.exec_driver_sql(f"SET search_path TO {schema}, public")
            await session.execute(text(f"SET search_path TO {schema}, public"))
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_public_db() -> AsyncGenerator[AsyncSession, None]:
    """Session pinned to public schema (for tenant lookups)."""
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def make_tenant_session(schema: str) -> AsyncSession:
    """
    Create an AsyncSession that always re-applies SET search_path after every
    commit (i.e. after every new connection checkout from the pool).
    Use as: async with make_tenant_session(schema) as db: ...
    """
    session = AsyncSessionLocal()

    @event.listens_for(session.sync_session, "after_begin")
    def _set_search_path(sess, transaction, connection):
        connection.exec_driver_sql(f"SET search_path TO {schema}, public")

    return session
