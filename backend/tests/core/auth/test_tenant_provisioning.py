"""Integration tests for the full tenant provisioning flow.

These tests exercise the real database (Alembic migrations applied) and the
real FastAPI app — no mocks.  They live in tests/core/auth/ so the root
conftest's ``setup_public_schema`` session fixture applies (the
tests/core/tenants/conftest.py no-op override does NOT apply here).

Covered scenarios
-----------------
1. Super admin POST /tenants returns 201 and ACTIVE tenant.
2. New tenant schema is created in PostgreSQL.
3. Initial admin user exists in the tenant schema with correct attributes.
4. Tenant admin can login immediately with the provisioned password (no 401).
5. must_change_password is True for the seeded admin (first-login gate).
6. No manual DB script is required — everything flows through the API.
"""

import random
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.auth.security import create_access_token, hash_password
from app.main import app

_BACKEND_DIR = str(Path(__file__).parent.parent.parent)

_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"statement_cache_size": 0},
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

# Unique slug/schema per test-run to avoid cross-test pollution.
# Slug is derived by generate_slug("Provisioning Test <id>") → "provisioning-test-<id>".
_RUN_ID = uuid.uuid4().hex[:8]
SLUG = f"provisioning-test-{_RUN_ID}"
SCHEMA = f"tenant_provisioning_test_{_RUN_ID}"
ADMIN_EMAIL = f"admin-{_RUN_ID}@provtest.edu"
ADMIN_PASSWORD = "Prov1234!"
ADMIN_FULL_NAME = "Provisioning Test Admin"
TENANT_NAME = f"Provisioning Test {_RUN_ID}"


def _run_alembic(target: str, schema: str | None = None) -> None:
    import os
    env = {**os.environ, "ALEMBIC_TARGET": target}
    if schema:
        env["TENANT_SCHEMA"] = schema
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="module", autouse=True)
def _setup_public(setup_public_schema):  # noqa: ARG001 — just ensures public schema is ready
    pass


@pytest_asyncio.fixture(scope="module")
async def async_client_module():
    ip = f"10.{random.randint(1, 254)}.{random.randint(1, 254)}.1"
    transport = ASGITransport(app=app, client=(ip, 9000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(scope="module")
async def platform_user():
    uid = uuid.uuid4()
    email = f"superadmin-prov-{uid.hex[:8]}@test.com"
    pw = "SuperAdmin1234!"
    pw_hash = hash_password(pw)
    async with _Session() as session:
        async with session.begin():
            await session.execute(
                text(
                    "INSERT INTO public.platform_users "
                    "(id, email, password_hash, full_name, is_active) "
                    "VALUES (:id, :email, :hash, :name, true)"
                ),
                {"id": str(uid), "email": email, "hash": pw_hash, "name": "Super Admin Prov"},
            )
    yield {"id": uid, "email": email, "password": pw}
    async with _Session() as session:
        async with session.begin():
            await session.execute(
                text("DELETE FROM public.platform_users WHERE id = :id"),
                {"id": str(uid)},
            )


def _platform_headers(user: dict) -> dict:
    token = create_access_token({
        "sub": str(user["id"]),
        "tenant_id": None,
        "schema_name": None,
        "role": "SUPER_ADMIN",
        "email": user["email"],
    })
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="module")
async def provisioned_tenant(async_client_module, platform_user):
    """Call POST /tenants via the API and yield the response JSON.  Teardown drops the schema."""
    resp = await async_client_module.post(
        "/tenants",
        json={
            "name": TENANT_NAME,
            "admin_email": ADMIN_EMAIL,
            "admin_password": ADMIN_PASSWORD,
            "admin_full_name": ADMIN_FULL_NAME,
        },
        headers=_platform_headers(platform_user),
    )
    assert resp.status_code == 201, f"Provisioning failed: {resp.text}"
    data = resp.json()
    yield data
    # Teardown: drop the tenant schema and deactivate the tenant record.
    async with _Session() as session:
        async with session.begin():
            await session.execute(
                text("DELETE FROM public.refresh_token_index WHERE schema_name = :s"),
                {"s": data["schema_name"]},
            )
            await session.execute(
                text("UPDATE public.tenants SET is_active = false WHERE slug = :slug"),
                {"slug": data["slug"]},
            )
            await session.execute(text(f"DROP SCHEMA IF EXISTS {data['schema_name']} CASCADE"))


# ---------------------------------------------------------------------------
# Test 1 — Super admin creates tenant and gets back an ACTIVE response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_tenant_returns_active(provisioned_tenant):
    assert provisioned_tenant["status"] == "ACTIVE"
    assert provisioned_tenant["is_active"] is True
    assert provisioned_tenant["slug"] == SLUG
    assert provisioned_tenant["schema_name"] == SCHEMA


# ---------------------------------------------------------------------------
# Test 2 — New tenant schema exists in PostgreSQL
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tenant_schema_exists(provisioned_tenant):
    schema = provisioned_tenant["schema_name"]
    async with _Session() as session:
        async with session.begin():
            result = await session.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name = :s"
                ),
                {"s": schema},
            )
            row = result.scalar_one_or_none()
    assert row == schema, f"Schema {schema!r} not found in information_schema"


# ---------------------------------------------------------------------------
# Test 3 — Initial admin user exists in the tenant schema with correct attributes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_user_exists_in_tenant_schema(provisioned_tenant):
    schema = provisioned_tenant["schema_name"]
    async with _Session() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL search_path = {schema}, public")
            )
            result = await session.execute(
                text(
                    "SELECT email, role, is_active, must_change_password "
                    "FROM users WHERE email = :email"
                ),
                {"email": ADMIN_EMAIL},
            )
            row = result.mappings().one_or_none()

    assert row is not None, f"Admin user {ADMIN_EMAIL!r} not found in {schema}"
    assert row["email"] == ADMIN_EMAIL
    assert row["role"] == "ADMIN"
    assert row["is_active"] is True
    assert row["must_change_password"] is True


# ---------------------------------------------------------------------------
# Test 4 — Tenant admin can login immediately (no 401)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tenant_admin_can_login(provisioned_tenant, async_client_module):
    slug = provisioned_tenant["slug"]
    resp = await async_client_module.post(
        "/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Tenant-Slug": slug},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


# ---------------------------------------------------------------------------
# Test 5 — must_change_password is set → first_login gate fires after login
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_first_login_gate_is_active(provisioned_tenant, async_client_module):
    slug = provisioned_tenant["slug"]
    login_resp = await async_client_module.post(
        "/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Tenant-Slug": slug},
    )
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]

    me_resp = await async_client_module.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": slug,
        },
    )
    assert me_resp.status_code == 200
    me = me_resp.json()
    assert me["must_change_password"] is True, "must_change_password should be True for seeded admin"
    assert me["first_login"] is True, "first_login gate should be active until password is changed"


# ---------------------------------------------------------------------------
# Test 6 — After changing password, must_change_password clears (no manual DB needed)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_must_change_password_clears_on_change(provisioned_tenant, async_client_module):
    slug = provisioned_tenant["slug"]
    schema = provisioned_tenant["schema_name"]

    login_resp = await async_client_module.post(
        "/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Tenant-Slug": slug},
    )
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]

    change_resp = await async_client_module.post(
        "/auth/change-password",
        json={"current_password": ADMIN_PASSWORD, "new_password": "NewProv1234!"},
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Slug": slug,
        },
    )
    assert change_resp.status_code == 200, f"change-password failed: {change_resp.text}"

    # Verify DB state directly — no manual script required
    async with _Session() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL search_path = {schema}, public")
            )
            result = await session.execute(
                text(
                    "SELECT must_change_password, password_changed_at "
                    "FROM users WHERE email = :email"
                ),
                {"email": ADMIN_EMAIL},
            )
            row = result.mappings().one()

    assert row["must_change_password"] is False, "must_change_password should clear after change"
    assert row["password_changed_at"] is not None, "password_changed_at should be set"
