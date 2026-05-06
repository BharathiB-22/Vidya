import asyncio
import os
import re
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings
from app.database import Base
from app.core.auth import models  # noqa: F401 — registers all models with Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

ALEMBIC_TARGET = os.environ.get("ALEMBIC_TARGET", "")
TENANT_SCHEMA = os.environ.get("TENANT_SCHEMA", "")


def get_version_locations() -> str:
    base = os.path.dirname(__file__)
    if ALEMBIC_TARGET == "public":
        return os.path.join(base, "public_versions")
    elif ALEMBIC_TARGET == "tenant":
        return os.path.join(base, "tenant_versions")
    else:
        raise RuntimeError(
            "ALEMBIC_TARGET must be set to 'public' or 'tenant'. "
            "Example: ALEMBIC_TARGET=public alembic upgrade head"
        )


if ALEMBIC_TARGET in ("public", "tenant"):
    from pathlib import Path
    context.script._version_locations = [Path(get_version_locations())]


def run_migrations_offline() -> None:
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_locations=get_version_locations(),
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    kw: dict = dict(
        connection=connection,
        target_metadata=target_metadata,
        version_locations=get_version_locations(),
    )
    if ALEMBIC_TARGET == "tenant" and TENANT_SCHEMA:
        kw["version_table_schema"] = TENANT_SCHEMA
    context.configure(**kw)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(settings.DATABASE_URL, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        if ALEMBIC_TARGET == "tenant":
            if not TENANT_SCHEMA:
                raise RuntimeError("TENANT_SCHEMA must be set when ALEMBIC_TARGET=tenant")
            if not re.match(r"^tenant_[a-z0-9_]+$", TENANT_SCHEMA):
                raise RuntimeError(f"Invalid TENANT_SCHEMA: {TENANT_SCHEMA}")
            await connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {TENANT_SCHEMA}"))
            await connection.execute(text(f"SET search_path = {TENANT_SCHEMA}, public"))
            await connection.commit()
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
