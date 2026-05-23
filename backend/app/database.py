import re
from contextvars import ContextVar
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    connect_args={"statement_cache_size": 0},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()

# Per-async-task ContextVar holding the tenant schema for the current request.
# Set by get_tenant_db_dep / get_tenant_context_dep before yielding a session.
# Read by the engine "begin" event below to inject SET LOCAL search_path at
# the start of EVERY database transaction, which is the only correct approach
# with PgBouncer in transaction pooling mode: each COMMIT returns the backend
# connection to PgBouncer's pool and the next BEGIN may land on a different
# backend that has no knowledge of the previous session-level search_path.
_tenant_schema_ctx: ContextVar[str | None] = ContextVar("_tenant_schema_ctx", default=None)


@event.listens_for(engine.sync_engine, "begin")
def _inject_search_path(conn) -> None:
    """Inject SET LOCAL search_path at the start of every DB transaction.

    Fires for every BEGIN: initial autobegin, explicit session.begin(), and each
    autobegin that follows a session.commit().  SET LOCAL confines the setting to
    the current transaction, which is the only pgbouncer-transaction-mode-safe
    option — after each COMMIT the backend connection may be recycled and the
    next client gets a fresh connection with search_path = public.
    """
    schema = _tenant_schema_ctx.get()
    if schema:
        conn.exec_driver_sql(f"SET LOCAL search_path TO {schema}, public")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_tenant_db(schema_name: str) -> AsyncGenerator[AsyncSession, None]:
    """Async generator for tenant-scoped DB sessions (used by Celery workers).

    Sets _tenant_schema_ctx so the engine begin event injects the correct
    search_path into every transaction for the duration of the generator.
    """
    if not re.match(r"^tenant_[a-z0-9_]+$", schema_name):
        raise ValueError(f"Invalid schema name: {schema_name}")
    token = _tenant_schema_ctx.set(schema_name)
    try:
        async with AsyncSessionLocal() as session:
            yield session
    finally:
        _tenant_schema_ctx.reset(token)
