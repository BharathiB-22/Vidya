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

_BACKEND_DIR = str(Path(__file__).parent.parent)
_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"statement_cache_size": 0},
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

SCHEMA_A = "tenant_test_a"
SCHEMA_B = "tenant_test_b"
SLUG_A = "test-tenant-a"
SLUG_B = "test-tenant-b"


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


@pytest.fixture(scope="session", autouse=True)
def setup_public_schema():
    _run_alembic("public")


@pytest_asyncio.fixture
async def test_tenant_a(setup_public_schema):
    new_id = uuid.uuid4()
    _run_alembic("tenant", SCHEMA_A)
    async with _Session() as session:
        async with session.begin():
            await session.execute(
                text(
                    "INSERT INTO public.tenants (id, slug, name, schema_name, is_active) "
                    "VALUES (:id, :slug, :name, :schema, true) "
                    "ON CONFLICT (slug) DO UPDATE SET is_active = true, "
                    "schema_name = EXCLUDED.schema_name"
                ),
                {"id": str(new_id), "slug": SLUG_A, "name": "Test Tenant A", "schema": SCHEMA_A},
            )
            result = await session.execute(
                text("SELECT id FROM public.tenants WHERE slug = :slug"),
                {"slug": SLUG_A},
            )
            tenant_id = uuid.UUID(str(result.scalar()))
    yield {"id": tenant_id, "slug": SLUG_A, "schema_name": SCHEMA_A}
    async with _Session() as session:
        async with session.begin():
            await session.execute(
                text("DELETE FROM public.refresh_token_index WHERE schema_name = :s"),
                {"s": SCHEMA_A},
            )
            # Do not DELETE from public.tenants — audit_logs.tenant_id has an
            # ON DELETE SET NULL FK, which becomes an UPDATE on audit_logs and is
            # blocked by the H05-06 append-only trigger.  Deactivating the tenant
            # is sufficient isolation; ON CONFLICT DO UPDATE in setup re-activates.
            await session.execute(
                text("UPDATE public.tenants SET is_active = false WHERE slug = :slug"),
                {"slug": SLUG_A},
            )
            await session.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA_A} CASCADE"))


@pytest_asyncio.fixture
async def test_tenant_b(setup_public_schema):
    new_id = uuid.uuid4()
    _run_alembic("tenant", SCHEMA_B)
    async with _Session() as session:
        async with session.begin():
            await session.execute(
                text(
                    "INSERT INTO public.tenants (id, slug, name, schema_name, is_active) "
                    "VALUES (:id, :slug, :name, :schema, true) "
                    "ON CONFLICT (slug) DO UPDATE SET is_active = true, "
                    "schema_name = EXCLUDED.schema_name"
                ),
                {"id": str(new_id), "slug": SLUG_B, "name": "Test Tenant B", "schema": SCHEMA_B},
            )
            result = await session.execute(
                text("SELECT id FROM public.tenants WHERE slug = :slug"),
                {"slug": SLUG_B},
            )
            tenant_id = uuid.UUID(str(result.scalar()))
    yield {"id": tenant_id, "slug": SLUG_B, "schema_name": SCHEMA_B}
    async with _Session() as session:
        async with session.begin():
            await session.execute(
                text("DELETE FROM public.refresh_token_index WHERE schema_name = :s"),
                {"s": SCHEMA_B},
            )
            await session.execute(
                text("UPDATE public.tenants SET is_active = false WHERE slug = :slug"),
                {"slug": SLUG_B},
            )
            await session.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA_B} CASCADE"))


async def _insert_tenant_user(
    schema_name: str, email: str, password: str, role: str, full_name: str
) -> dict:
    user_id = uuid.uuid4()
    pw_hash = hash_password(password)
    async with _Session() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL search_path = {schema_name}, public")
            )
            await session.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, role, full_name, is_active) "
                    "VALUES (:id, :email, :hash, :role, :name, true)"
                ),
                {"id": str(user_id), "email": email, "hash": pw_hash, "role": role, "name": full_name},
            )
    return {"id": user_id, "email": email, "password": password, "role": role, "full_name": full_name}


@pytest_asyncio.fixture
async def admin_user_a(test_tenant_a):
    user = await _insert_tenant_user(SCHEMA_A, "admin_a@test.com", "Admin1234!", "ADMIN", "Admin A")
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


@pytest_asyncio.fixture
async def faculty_user_a(test_tenant_a):
    user = await _insert_tenant_user(SCHEMA_A, "faculty_a@test.com", "Faculty1234!", "FACULTY", "Faculty A")
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


@pytest_asyncio.fixture
async def student_user_a(test_tenant_a):
    user = await _insert_tenant_user(SCHEMA_A, "student_a@test.com", "Student1234!", "STUDENT", "Student A")
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


@pytest_asyncio.fixture
async def admin_user_b(test_tenant_b):
    user = await _insert_tenant_user(SCHEMA_B, "admin_b@test.com", "Admin1234!", "ADMIN", "Admin B")
    yield {**user, "tenant_id": test_tenant_b["id"], "schema_name": SCHEMA_B, "slug": SLUG_B}


@pytest_asyncio.fixture
async def faculty_user_b(test_tenant_b):
    user = await _insert_tenant_user(SCHEMA_B, "faculty_b@test.com", "Faculty1234!", "FACULTY", "Faculty B")
    yield {**user, "tenant_id": test_tenant_b["id"], "schema_name": SCHEMA_B, "slug": SLUG_B}


@pytest_asyncio.fixture
async def test_platform_user(setup_public_schema):
    user_id = uuid.uuid4()
    email = f"superadmin_{user_id.hex[:8]}@test.com"
    password = "SuperAdmin1234!"
    pw_hash = hash_password(password)
    async with _Session() as session:
        async with session.begin():
            await session.execute(
                text(
                    "INSERT INTO public.platform_users "
                    "(id, email, password_hash, full_name, is_active) "
                    "VALUES (:id, :email, :hash, :name, true)"
                ),
                {"id": str(user_id), "email": email, "hash": pw_hash, "name": "Super Admin"},
            )
    yield {"id": user_id, "email": email, "password": password, "full_name": "Super Admin"}
    async with _Session() as session:
        async with session.begin():
            await session.execute(
                text("DELETE FROM public.platform_refresh_tokens WHERE user_id = :id"),
                {"id": str(user_id)},
            )
            await session.execute(
                text("DELETE FROM public.platform_otp_codes WHERE user_id = :id"),
                {"id": str(user_id)},
            )
            await session.execute(
                text(
                    "DELETE FROM public.refresh_token_index "
                    "WHERE schema_name IS NULL AND user_id = :id"
                ),
                {"id": str(user_id)},
            )
            await session.execute(
                text("DELETE FROM public.platform_users WHERE id = :id"),
                {"id": str(user_id)},
            )


@pytest_asyncio.fixture
async def db():
    async with _Session() as session:
        yield session


@pytest_asyncio.fixture
async def async_client():
    ip = f"10.{random.randint(1, 254)}.{random.randint(1, 254)}.1"
    transport = ASGITransport(app=app, client=(ip, 9000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def make_tenant_headers(user: dict) -> dict:
    token = create_access_token({
        "sub": str(user["id"]),
        "tenant_id": str(user["tenant_id"]),
        "schema_name": user["schema_name"],
        "role": user["role"],
        "email": user["email"],
    })
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": user["slug"]}


def make_platform_headers(user: dict) -> dict:
    token = create_access_token({
        "sub": str(user["id"]),
        "tenant_id": None,
        "schema_name": None,
        "role": "SUPER_ADMIN",
        "email": user["email"],
    })
    return {"Authorization": f"Bearer {token}"}
