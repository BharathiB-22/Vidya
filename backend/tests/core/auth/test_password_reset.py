import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.core.auth.security import hash_otp
from tests.conftest import SCHEMA_A, SLUG_A, _Session


def _extract_otp(captured_out: str) -> str:
    for line in captured_out.splitlines():
        if "[DEV]" in line and "OTP" in line:
            return line.strip().rsplit(": ", 1)[-1]
    raise ValueError(f"OTP not found in output: {captured_out!r}")


async def test_reset_happy_path(async_client, test_tenant_a, admin_user_a, capsys):
    # 1. Request OTP
    r1 = await async_client.post(
        "/auth/password-reset/request",
        json={"email": admin_user_a["email"]},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert r1.status_code == 200
    otp = _extract_otp(capsys.readouterr().out)

    # 2. Verify OTP → get reset token
    r2 = await async_client.post(
        "/auth/password-reset/verify",
        json={"email": admin_user_a["email"], "otp": otp},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert r2.status_code == 200
    reset_token = r2.json()["reset_token"]

    # 3. Confirm reset
    new_password = "NewPassword1234!"
    r3 = await async_client.post(
        "/auth/password-reset/confirm",
        json={"reset_token": reset_token, "new_password": new_password},
    )
    assert r3.status_code == 200

    # 4. Login with new password
    r4 = await async_client.post(
        "/auth/login",
        json={"email": admin_user_a["email"], "password": new_password},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert r4.status_code == 200


async def test_reset_tokens_revoked_after_reset(async_client, test_tenant_a, admin_user_a, capsys):
    # Login first to get a refresh token
    login = await async_client.post(
        "/auth/login",
        json={"email": admin_user_a["email"], "password": admin_user_a["password"]},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    old_refresh = login.json()["refresh_token"]

    # Full reset flow
    await async_client.post(
        "/auth/password-reset/request",
        json={"email": admin_user_a["email"]},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    otp = _extract_otp(capsys.readouterr().out)
    r2 = await async_client.post(
        "/auth/password-reset/verify",
        json={"email": admin_user_a["email"], "otp": otp},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    reset_token = r2.json()["reset_token"]
    await async_client.post(
        "/auth/password-reset/confirm",
        json={"reset_token": reset_token, "new_password": "Another1234!"},
    )

    # Old refresh token must be revoked
    r = await async_client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 401


async def test_reset_otp_wrong_once(async_client, test_tenant_a, admin_user_a, capsys):
    await async_client.post(
        "/auth/password-reset/request",
        json={"email": admin_user_a["email"]},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    capsys.readouterr()  # discard OTP output

    # Wrong OTP — should fail but OTP still active
    r = await async_client.post(
        "/auth/password-reset/verify",
        json={"email": admin_user_a["email"], "otp": "000000"},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert r.status_code == 401

    # attempts incremented in DB
    async with _Session() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            row = await session.execute(
                text("SELECT attempts FROM otp_codes WHERE is_used = false ORDER BY created_at DESC LIMIT 1")
            )
            attempts = row.scalar_one_or_none()
    assert attempts == 1


async def test_reset_otp_max_attempts(async_client, test_tenant_a, admin_user_a, capsys):
    await async_client.post(
        "/auth/password-reset/request",
        json={"email": admin_user_a["email"]},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    capsys.readouterr()

    for _ in range(3):
        await async_client.post(
            "/auth/password-reset/verify",
            json={"email": admin_user_a["email"], "otp": "000000"},
            headers={"X-Tenant-Slug": SLUG_A},
        )

    # OTP should now be consumed — any further attempt fails
    r = await async_client.post(
        "/auth/password-reset/verify",
        json={"email": admin_user_a["email"], "otp": "000000"},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert r.status_code == 401


async def test_reset_otp_expired(async_client, test_tenant_a, admin_user_a):
    user_id = admin_user_a["id"]
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    otp_plain = "123456"
    otp_hash = hash_otp(otp_plain)

    async with _Session() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            await session.execute(
                text(
                    "INSERT INTO otp_codes (id, user_id, otp_hash, purpose, expires_at, is_used, attempts) "
                    "VALUES (:id, :uid, :hash, 'PASSWORD_RESET', :exp, false, 0)"
                ),
                {"id": str(uuid.uuid4()), "uid": str(user_id), "hash": otp_hash, "exp": past},
            )

    r = await async_client.post(
        "/auth/password-reset/verify",
        json={"email": admin_user_a["email"], "otp": otp_plain},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert r.status_code == 401


async def test_reset_otp_second_use(async_client, test_tenant_a, admin_user_a, capsys):
    await async_client.post(
        "/auth/password-reset/request",
        json={"email": admin_user_a["email"]},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    otp = _extract_otp(capsys.readouterr().out)

    # First use — succeeds
    r1 = await async_client.post(
        "/auth/password-reset/verify",
        json={"email": admin_user_a["email"], "otp": otp},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert r1.status_code == 200

    # Second use — must fail
    r2 = await async_client.post(
        "/auth/password-reset/verify",
        json={"email": admin_user_a["email"], "otp": otp},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert r2.status_code == 401


async def test_reset_unknown_email_silent(async_client, test_tenant_a):
    r = await async_client.post(
        "/auth/password-reset/request",
        json={"email": "ghost@test.com"},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert r.status_code == 200  # no enumeration


async def test_reset_token_reuse_rejected(async_client, test_tenant_a, admin_user_a, capsys):
    await async_client.post(
        "/auth/password-reset/request",
        json={"email": admin_user_a["email"]},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    otp = _extract_otp(capsys.readouterr().out)
    r2 = await async_client.post(
        "/auth/password-reset/verify",
        json={"email": admin_user_a["email"], "otp": otp},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    reset_token = r2.json()["reset_token"]

    # First confirm — succeeds
    r3 = await async_client.post(
        "/auth/password-reset/confirm",
        json={"reset_token": reset_token, "new_password": "First1234!"},
    )
    assert r3.status_code == 200

    # Second confirm with same token — iat_cutoff check must reject
    r4 = await async_client.post(
        "/auth/password-reset/confirm",
        json={"reset_token": reset_token, "new_password": "Second1234!"},
    )
    assert r4.status_code == 401
    assert r4.json()["error"] == "INVALID_TOKEN"
