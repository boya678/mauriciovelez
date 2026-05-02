"""Alembic async env — manages only the public schema (tenants table).

Tenant schemas are created/migrated dynamically via the tenants API.
"""
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import metadata from models so autogenerate works
from app.db.base import Base  # noqa: F401
from app.models import *  # noqa: F401, F403 — registers all mappers

# --------------------------------------------------------------------------- #
# Alembic Config object
# --------------------------------------------------------------------------- #
config = context.config

# Override sqlalchemy.url with the value from the environment / .env so we
# don't hard-code credentials in alembic.ini.
database_url = os.environ.get("DATABASE_URL", "")
if database_url:
    # asyncpg driver needed at runtime but synchronous psycopg2 for migrations;
    # swap the driver so Alembic can use its sync rendering pipeline.
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# --------------------------------------------------------------------------- #
# Offline migrations
# --------------------------------------------------------------------------- #
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema="public",
    )
    with context.begin_transaction():
        context.run_migrations()


# --------------------------------------------------------------------------- #
# Online migrations — sync runner called from asyncio
# --------------------------------------------------------------------------- #
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema="public",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine (asyncpg)."""
    database_url_async = os.environ.get("DATABASE_URL", "")
    if not database_url_async:
        raise RuntimeError("DATABASE_URL env var is not set")

    connectable = async_engine_from_config(
        {"sqlalchemy.url": database_url_async},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
