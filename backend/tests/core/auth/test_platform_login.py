from jose import jwt

from app.config import settings
from tests.conftest import SCHEMA_A, _Session
from sqlalchemy import text


async def test_platform_login_happy_path(async_client, test_platform_user):
    resp = await async_client.post(
        "/platform/auth/login",
        json={"email": test_platform_user["email"], "password": test_platform_user["password"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data

    payload = jwt.decode(data["access_token"], settings.JWT_SECRET, algorithms=["HS256"])
    assert payload["schema_name"] is None
    assert payload["tenant_id"] is None
    assert payload["role"] == "SUPER_ADMIN"


async def test_platform_login_wrong_password(async_client, test_platform_user):
    resp = await async_client.post(
        "/platform/auth/login",
        json={"email": test_platform_user["email"], "password": "wrongpassword"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "INVALID_CREDENTIALS"


async def test_platform_login_no_tenant_schema_touched(async_client, test_platform_user, test_tenant_a):
    # Login as platform user
    resp = await async_client.post(
        "/platform/auth/login",
        json={"email": test_platform_user["email"], "password": test_platform_user["password"]},
    )
    assert resp.status_code == 200

    # Tenant A users table should be empty (no login recorded there)
    async with _Session() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            row = await session.execute(text("SELECT COUNT(*) FROM refresh_tokens"))
            count = row.scalar()
    assert count == 0
