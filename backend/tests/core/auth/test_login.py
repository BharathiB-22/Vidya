import pytest
from sqlalchemy import text

from tests.conftest import SCHEMA_A, SLUG_A, _Session


async def test_login_happy_path(async_client, test_tenant_a, admin_user_a):
    resp = await async_client.post(
        "/auth/login",
        json={"email": admin_user_a["email"], "password": admin_user_a["password"]},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0

    # last_login_at updated in tenant schema
    async with _Session() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            row = await session.execute(
                text("SELECT last_login_at FROM users WHERE email = :e"),
                {"e": admin_user_a["email"]},
            )
            last_login = row.scalar_one_or_none()
    assert last_login is not None


@pytest.mark.xfail(
    reason="H05-DEF-01: error envelope format refactor deferred from H05-07",
    strict=False,
)
async def test_login_wrong_password(async_client, test_tenant_a, admin_user_a):
    resp = await async_client.post(
        "/auth/login",
        json={"email": admin_user_a["email"], "password": "wrongpassword"},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "INVALID_CREDENTIALS"


@pytest.mark.xfail(
    reason="H05-DEF-01: error envelope format refactor deferred from H05-07",
    strict=False,
)
async def test_login_unknown_email(async_client, test_tenant_a):
    resp = await async_client.post(
        "/auth/login",
        json={"email": "nobody@test.com", "password": "password"},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "INVALID_CREDENTIALS"


async def test_login_inactive_user(async_client, test_tenant_a, admin_user_a):
    async with _Session() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            await session.execute(
                text("UPDATE users SET is_active = false WHERE email = :e"),
                {"e": admin_user_a["email"]},
            )
    try:
        resp = await async_client.post(
            "/auth/login",
            json={"email": admin_user_a["email"], "password": admin_user_a["password"]},
            headers={"X-Tenant-Slug": SLUG_A},
        )
        assert resp.status_code == 401
    finally:
        async with _Session() as session:
            async with session.begin():
                await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
                await session.execute(
                    text("UPDATE users SET is_active = true WHERE email = :e"),
                    {"e": admin_user_a["email"]},
                )


async def test_login_missing_tenant_slug(async_client):
    resp = await async_client.post(
        "/auth/login",
        json={"email": "test@test.com", "password": "password"},
    )
    assert resp.status_code == 422


@pytest.mark.xfail(
    reason="H05-DEF-01: error envelope format refactor deferred from H05-07",
    strict=False,
)
async def test_login_unknown_slug(async_client):
    resp = await async_client.post(
        "/auth/login",
        json={"email": "test@test.com", "password": "password"},
        headers={"X-Tenant-Slug": "nonexistent-slug-xyz"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "TENANT_NOT_FOUND"


@pytest.mark.xfail(
    reason="H05-DEF-01: error envelope format refactor deferred from H05-07",
    strict=False,
)
async def test_login_inactive_tenant(async_client, test_tenant_a, admin_user_a):
    async with _Session() as session:
        async with session.begin():
            await session.execute(
                text("UPDATE public.tenants SET is_active = false WHERE slug = :slug"),
                {"slug": SLUG_A},
            )
    try:
        resp = await async_client.post(
            "/auth/login",
            json={"email": admin_user_a["email"], "password": admin_user_a["password"]},
            headers={"X-Tenant-Slug": SLUG_A},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"] == "TENANT_INACTIVE"
    finally:
        async with _Session() as session:
            async with session.begin():
                await session.execute(
                    text("UPDATE public.tenants SET is_active = true WHERE slug = :slug"),
                    {"slug": SLUG_A},
                )
