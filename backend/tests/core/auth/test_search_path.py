"""
Regression tests for BUG-H13-03-01: tenant search_path must be injected at
the start of EVERY database transaction, not just once per session.

Root cause: PgBouncer runs in transaction pooling mode. After each COMMIT the
backend PostgreSQL connection is returned to PgBouncer's pool; the next BEGIN
may land on a different backend with search_path = public.

Fix: _tenant_schema_ctx ContextVar + engine.sync_engine "begin" event in
database.py emit SET LOCAL search_path at the start of every transaction.
"""
import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal, _tenant_schema_ctx
from tests.conftest import SCHEMA_A, SCHEMA_B

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _show_search_path(session) -> str:
    result = await session.execute(text("SHOW search_path"))
    return result.scalar()


# ---------------------------------------------------------------------------
# Core: search_path is injected at every BEGIN
# ---------------------------------------------------------------------------


async def test_search_path_set_on_first_transaction(test_tenant_a):
    """ContextVar triggers SET LOCAL on first transaction autobegin."""
    token = _tenant_schema_ctx.set(SCHEMA_A)
    try:
        async with AsyncSessionLocal() as session:
            path = await _show_search_path(session)
            assert SCHEMA_A in path, f"Expected {SCHEMA_A!r} in search_path, got {path!r}"
    finally:
        _tenant_schema_ctx.reset(token)


async def test_search_path_re_injected_after_commit(test_tenant_a):
    """After session.commit() the next autobegin must also get the correct search_path.

    This is the exact scenario that failed under PgBouncer transaction mode:
    commit() recycles the backend connection; the subsequent BEGIN landed on a
    fresh backend with search_path = public.
    """
    token = _tenant_schema_ctx.set(SCHEMA_A)
    try:
        async with AsyncSessionLocal() as session:
            # First transaction
            path1 = await _show_search_path(session)
            assert SCHEMA_A in path1, f"tx1 path={path1!r}"
            await session.commit()

            # Second transaction — must also see tenant schema
            path2 = await _show_search_path(session)
            assert SCHEMA_A in path2, f"tx2 path={path2!r} (regression: search_path lost after commit)"

            await session.commit()

            # Third transaction — belt and braces
            path3 = await _show_search_path(session)
            assert SCHEMA_A in path3, f"tx3 path={path3!r}"
    finally:
        _tenant_schema_ctx.reset(token)


async def test_search_path_not_polluted_without_context():
    """Without ContextVar set, the begin event must not alter search_path."""
    # Explicitly clear ContextVar — robust against combined-run pollution from
    # pytest-asyncio session-scoped loop sharing context across tests.
    token = _tenant_schema_ctx.set(None)
    try:
        async with AsyncSessionLocal() as session:
            path = await _show_search_path(session)
            assert SCHEMA_A not in path, f"search_path={path!r} should not contain {SCHEMA_A!r} without ctx"
            assert SCHEMA_B not in path, f"search_path={path!r} should not contain {SCHEMA_B!r} without ctx"
    finally:
        _tenant_schema_ctx.reset(token)


async def test_search_path_isolated_between_tenants(test_tenant_a, test_tenant_b):
    """Two concurrent tenant contexts must not bleed into each other."""
    token_a = _tenant_schema_ctx.set(SCHEMA_A)
    try:
        async with AsyncSessionLocal() as session_a:
            path_a = await _show_search_path(session_a)
            assert SCHEMA_A in path_a
            assert SCHEMA_B not in path_a
    finally:
        _tenant_schema_ctx.reset(token_a)

    token_b = _tenant_schema_ctx.set(SCHEMA_B)
    try:
        async with AsyncSessionLocal() as session_b:
            path_b = await _show_search_path(session_b)
            assert SCHEMA_B in path_b
            assert SCHEMA_A not in path_b
    finally:
        _tenant_schema_ctx.reset(token_b)


# ---------------------------------------------------------------------------
# End-to-end: notifications endpoint survives internal transaction boundaries
# ---------------------------------------------------------------------------


async def test_notifications_endpoint_returns_200(async_client, test_tenant_a, faculty_user_a):
    """GET /notifications must return 200 even after the fix removes the upfront commit.

    Previously, get_tenant_db_dep set search_path + committed, which worked at
    low concurrency but failed under pgbouncer connection recycling.
    """
    from tests.conftest import make_tenant_headers
    headers = make_tenant_headers(faculty_user_a)
    resp = await async_client.get("/notifications?page=1&page_size=10", headers=headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "items" in data
    assert "total" in data


async def test_programs_endpoint_returns_200(async_client, test_tenant_a, faculty_user_a):
    """GET /programs must return 200 — it also failed under spike load."""
    from tests.conftest import make_tenant_headers
    headers = make_tenant_headers(faculty_user_a)
    resp = await async_client.get("/programs?page=1&page_size=10", headers=headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
