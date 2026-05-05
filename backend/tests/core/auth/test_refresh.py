import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.core.auth.security import hash_token, generate_refresh_token
from tests.conftest import SCHEMA_A, SLUG_A, _Session, make_platform_headers


async def _login(async_client, user):
    resp = await async_client.post(
        "/auth/login",
        json={"email": user["email"], "password": user["password"]},
        headers={"X-Tenant-Slug": user["slug"]},
    )
    assert resp.status_code == 200
    return resp.json()


async def test_refresh_happy_path(async_client, test_tenant_a, admin_user_a):
    tokens = await _login(async_client, admin_user_a)
    old_refresh = tokens["refresh_token"]
    old_hash = hash_token(old_refresh)

    resp = await async_client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["refresh_token"] != old_refresh

    # Old token should be gone from index
    async with _Session() as session:
        async with session.begin():
            row = await session.execute(
                text("SELECT 1 FROM public.refresh_token_index WHERE token_hash = :h"),
                {"h": old_hash},
            )
            assert row.scalar_one_or_none() is None

    # Old token revoked in tenant table
    async with _Session() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            row = await session.execute(
                text("SELECT is_revoked FROM refresh_tokens WHERE token_hash = :h"),
                {"h": old_hash},
            )
            assert row.scalar_one_or_none() is True


async def test_refresh_reuse_detection(async_client, test_tenant_a, admin_user_a):
    tokens = await _login(async_client, admin_user_a)
    refresh_token = tokens["refresh_token"]

    # First refresh — valid
    r1 = await async_client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r1.status_code == 200

    # Reuse old token — should trigger reuse detection
    r2 = await async_client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r2.status_code == 401
    assert r2.json()["detail"]["error"] == "INVALID_TOKEN"

    # New token from r1 should also be revoked (all tokens revoked)
    r3 = await async_client.post(
        "/auth/refresh", json={"refresh_token": r1.json()["refresh_token"]}
    )
    assert r3.status_code == 401


async def test_refresh_expired_token(async_client, test_tenant_a, admin_user_a):
    raw = generate_refresh_token()
    token_hash = hash_token(raw)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    user_id = admin_user_a["id"]

    async with _Session() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            await session.execute(
                text(
                    "INSERT INTO refresh_tokens "
                    "(id, user_id, token_hash, expires_at, is_revoked) "
                    "VALUES (:id, :uid, :hash, :exp, false)"
                ),
                {"id": str(uuid.uuid4()), "uid": str(user_id), "hash": token_hash, "exp": past},
            )
            await session.execute(
                text(
                    "INSERT INTO public.refresh_token_index (token_hash, schema_name, user_id) "
                    "VALUES (:hash, :schema, :uid)"
                ),
                {"hash": token_hash, "schema": SCHEMA_A, "uid": str(user_id)},
            )

    resp = await async_client.post("/auth/refresh", json={"refresh_token": raw})
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "INVALID_TOKEN"


async def test_refresh_bogus_token(async_client, test_tenant_a):
    resp = await async_client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "INVALID_TOKEN"


async def test_refresh_inactive_user(async_client, test_tenant_a, admin_user_a):
    tokens = await _login(async_client, admin_user_a)
    refresh_token = tokens["refresh_token"]

    async with _Session() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            await session.execute(
                text("UPDATE users SET is_active = false WHERE email = :e"),
                {"e": admin_user_a["email"]},
            )
    try:
        resp = await async_client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 401
    finally:
        async with _Session() as session:
            async with session.begin():
                await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
                await session.execute(
                    text("UPDATE users SET is_active = true WHERE email = :e"),
                    {"e": admin_user_a["email"]},
                )


async def test_refresh_super_admin_uses_platform_tables(async_client, test_platform_user, test_tenant_a):
    login = await async_client.post(
        "/platform/auth/login",
        json={"email": test_platform_user["email"], "password": test_platform_user["password"]},
    )
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    resp = await async_client.post("/platform/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200

    # Tenant A refresh_tokens table must be empty
    async with _Session() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            row = await session.execute(text("SELECT COUNT(*) FROM refresh_tokens"))
            assert row.scalar() == 0
