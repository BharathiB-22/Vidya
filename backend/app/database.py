import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import AsyncGenerator, Iterator

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


def bind_tenant_search_path(worker_engine) -> None:
    """Give a WORKER-OWNED engine the same per-transaction search_path as the API's.

    The request engine above gets `_inject_search_path` at import. The Celery workers
    do not use that engine — each builds its own (NullPool, because a pooled asyncpg
    connection cannot outlive the event loop `asyncio.run` creates per task) — so each
    of them also has to be told, or its transactions run with search_path = public.

    Being told ONCE per session is not enough, and this is the bug this function
    exists to close. A worker that opened a session, ran `SET search_path`, and then
    committed in the middle of its task got its connection returned to the pool at
    that commit — and NullPool does not return connections to a pool, it CLOSES them.
    The next statement opened a brand-new connection that had never heard of the SET,
    and every tenant table vanished: `relation "syllabus_units" does not exist`, from
    a schema in which that table demonstrably exists.

    So the schema is re-established at the start of EVERY transaction, which is the
    only thing a commit cannot undo. Idempotent — attaching twice would issue the SET
    twice per BEGIN, so a second call on the same engine is a no-op.
    """
    sync_engine = worker_engine.sync_engine
    if not event.contains(sync_engine, "begin", _inject_search_path):
        event.listen(sync_engine, "begin", _inject_search_path)


@contextmanager
def tenant_schema_scope(schema_name: str) -> Iterator[None]:
    """Run a block with every transaction scoped to `schema_name`.

    The Celery equivalent of `get_tenant_db_dep`: it sets the ContextVar that
    `_inject_search_path` reads, and unsets it afterwards so a worker process — which,
    unlike a request, is long-lived and serves every tenant in turn — cannot leak one
    tenant's schema into the next task it picks up.

    The engine backing the sessions inside the block must have had
    `bind_tenant_search_path` called on it, or nothing reads this ContextVar.
    """
    if not re.match(r"^tenant_[a-z0-9_]+$", schema_name):
        raise ValueError(f"Invalid schema name: {schema_name}")
    token = _tenant_schema_ctx.set(schema_name)
    try:
        yield
    finally:
        _tenant_schema_ctx.reset(token)


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
