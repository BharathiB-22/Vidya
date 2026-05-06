import uuid

import pytest
from sqlalchemy import text

from tests.conftest import SLUG_A, SLUG_B, _Session, make_platform_headers, make_tenant_headers

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_audit_logs(client, headers, **params) -> dict:
    resp = await client.get("/audit-logs", headers=headers, params=params)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    return resp.json()


def _extract_otp(captured_out: str) -> str:
    for line in captured_out.splitlines():
        if "[DEV]" in line and "OTP" in line:
            return line.strip().rsplit(": ", 1)[-1]
    raise ValueError(f"OTP not found in output: {captured_out!r}")


# ---------------------------------------------------------------------------
# Tenant auth audit events
# ---------------------------------------------------------------------------


async def test_login_success_writes_audit(async_client, test_tenant_a, admin_user_a, test_platform_user):
    platform_headers = make_platform_headers(test_platform_user)

    resp = await async_client.post(
        "/auth/login",
        json={"email": admin_user_a["email"], "password": admin_user_a["password"]},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 200

    logs = await _get_audit_logs(
        async_client, platform_headers,
        event_type="AUTH_LOGIN_SUCCESS",
        actor_user_id=str(admin_user_a["id"]),
    )
    assert logs["total"] >= 1
    entry = logs["items"][0]
    assert entry["tenant_id"] == str(admin_user_a["tenant_id"])
    assert entry["schema_name"] == admin_user_a["schema_name"]


async def test_login_failure_wrong_password_writes_audit(async_client, test_tenant_a, admin_user_a, test_platform_user):
    platform_headers = make_platform_headers(test_platform_user)

    resp = await async_client.post(
        "/auth/login",
        json={"email": admin_user_a["email"], "password": "WrongPassword999!"},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 401

    logs = await _get_audit_logs(
        async_client, platform_headers,
        event_type="AUTH_LOGIN_FAILURE",
        actor_user_id=str(admin_user_a["id"]),
    )
    assert logs["total"] >= 1
    entry = logs["items"][0]
    assert entry["metadata"]["reason"] == "invalid_password"


async def test_login_failure_unknown_email_writes_audit(async_client, test_tenant_a, test_platform_user):
    platform_headers = make_platform_headers(test_platform_user)
    ghost_email = f"ghost_{uuid.uuid4().hex[:8]}@test.com"

    resp = await async_client.post(
        "/auth/login",
        json={"email": ghost_email, "password": "anything"},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert resp.status_code == 401

    logs = await _get_audit_logs(
        async_client, platform_headers,
        event_type="AUTH_LOGIN_FAILURE",
        tenant_id=str(test_tenant_a["id"]),
        page_size=200,
    )
    null_actor_entries = [e for e in logs["items"] if e["actor_user_id"] is None]
    assert any(
        e["metadata"] and e["metadata"].get("attempted_email") == ghost_email
        for e in null_actor_entries
    )


# ---------------------------------------------------------------------------
# Platform auth audit events
# ---------------------------------------------------------------------------


async def test_platform_login_writes_audit(async_client, test_platform_user):
    platform_headers = make_platform_headers(test_platform_user)

    resp = await async_client.post(
        "/platform/auth/login",
        json={"email": test_platform_user["email"], "password": test_platform_user["password"]},
    )
    assert resp.status_code == 200

    logs = await _get_audit_logs(
        async_client, platform_headers,
        event_type="PLATFORM_LOGIN_SUCCESS",
        actor_user_id=str(test_platform_user["id"]),
    )
    assert logs["total"] >= 1
    entry = logs["items"][0]
    assert entry["tenant_id"] is None


# ---------------------------------------------------------------------------
# Token reuse detection
# ---------------------------------------------------------------------------


async def test_token_reuse_writes_audit(async_client, test_tenant_a, admin_user_a, test_platform_user):
    platform_headers = make_platform_headers(test_platform_user)

    login = await async_client.post(
        "/auth/login",
        json={"email": admin_user_a["email"], "password": admin_user_a["password"]},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert login.status_code == 200
    old_refresh_token = login.json()["refresh_token"]

    # First refresh — consumes and revokes old_refresh_token
    r1 = await async_client.post("/auth/refresh", json={"refresh_token": old_refresh_token})
    assert r1.status_code == 200

    # Reuse old (now revoked) token — triggers reuse detection
    r2 = await async_client.post("/auth/refresh", json={"refresh_token": old_refresh_token})
    assert r2.status_code == 401

    logs = await _get_audit_logs(
        async_client, platform_headers,
        event_type="AUTH_TOKEN_REUSE_DETECTED",
        actor_user_id=str(admin_user_a["id"]),
    )
    assert logs["total"] >= 1


# ---------------------------------------------------------------------------
# Password reset full flow
# ---------------------------------------------------------------------------


async def test_password_reset_full_flow_writes_audit(
    async_client, test_tenant_a, admin_user_a, test_platform_user, capsys
):
    platform_headers = make_platform_headers(test_platform_user)

    # Step 1: request OTP
    r1 = await async_client.post(
        "/auth/password-reset/request",
        json={"email": admin_user_a["email"]},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert r1.status_code == 200
    otp = _extract_otp(capsys.readouterr().out)

    # Step 2: verify OTP
    r2 = await async_client.post(
        "/auth/password-reset/verify",
        json={"email": admin_user_a["email"], "otp": otp},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    assert r2.status_code == 200
    reset_token = r2.json()["reset_token"]

    # Step 3: confirm reset
    r3 = await async_client.post(
        "/auth/password-reset/confirm",
        json={"reset_token": reset_token, "new_password": "NewPass1234!"},
    )
    assert r3.status_code == 200

    actor_id = str(admin_user_a["id"])

    requested = await _get_audit_logs(
        async_client, platform_headers,
        event_type="AUTH_PASSWORD_RESET_REQUESTED",
        actor_user_id=actor_id,
    )
    assert requested["total"] >= 1

    verified = await _get_audit_logs(
        async_client, platform_headers,
        event_type="AUTH_PASSWORD_RESET_VERIFIED",
        actor_user_id=actor_id,
    )
    assert verified["total"] >= 1

    completed = await _get_audit_logs(
        async_client, platform_headers,
        event_type="AUTH_PASSWORD_RESET_COMPLETED",
        actor_user_id=actor_id,
    )
    assert completed["total"] >= 1


# ---------------------------------------------------------------------------
# User management audit events
# ---------------------------------------------------------------------------


async def test_user_created_writes_audit(async_client, test_tenant_a, admin_user_a, test_platform_user):
    platform_headers = make_platform_headers(test_platform_user)
    admin_headers = make_tenant_headers(admin_user_a)
    new_email = f"faculty_{uuid.uuid4().hex[:8]}@test.com"

    resp = await async_client.post(
        "/admin/users",
        headers=admin_headers,
        json={"email": new_email, "password": "Faculty1234!", "role": "FACULTY", "full_name": "Test Faculty"},
    )
    assert resp.status_code == 201
    new_user_id = resp.json()["id"]

    logs = await _get_audit_logs(
        async_client, platform_headers,
        event_type="USER_CREATED",
        actor_user_id=str(admin_user_a["id"]),
    )
    assert logs["total"] >= 1
    entry = logs["items"][0]
    assert entry["target_id"] == new_user_id
    assert entry["metadata"]["role"] == "FACULTY"


async def test_user_role_changed_writes_audit(
    async_client, test_tenant_a, admin_user_a, faculty_user_a, test_platform_user
):
    platform_headers = make_platform_headers(test_platform_user)
    admin_headers = make_tenant_headers(admin_user_a)

    resp = await async_client.patch(
        f"/admin/users/{faculty_user_a['id']}",
        headers=admin_headers,
        json={"role": "DEAN"},
    )
    assert resp.status_code == 200

    logs = await _get_audit_logs(
        async_client, platform_headers,
        event_type="USER_ROLE_CHANGED",
        actor_user_id=str(admin_user_a["id"]),
    )
    assert logs["total"] >= 1
    entry = logs["items"][0]
    assert entry["metadata"]["changes"]["role"] == "DEAN"


async def test_user_deactivated_writes_audit(
    async_client, test_tenant_a, admin_user_a, faculty_user_a, test_platform_user
):
    platform_headers = make_platform_headers(test_platform_user)
    admin_headers = make_tenant_headers(admin_user_a)

    resp = await async_client.patch(
        f"/admin/users/{faculty_user_a['id']}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert resp.status_code == 200

    logs = await _get_audit_logs(
        async_client, platform_headers,
        event_type="USER_DEACTIVATED",
        actor_user_id=str(admin_user_a["id"]),
    )
    assert logs["total"] >= 1
    entry = logs["items"][0]
    assert entry["metadata"]["changes"]["is_active"] is False


# ---------------------------------------------------------------------------
# Multi-tenant isolation
# ---------------------------------------------------------------------------


async def test_tenant_admin_cannot_see_other_tenant_logs(
    async_client, admin_user_a, admin_user_b, test_platform_user
):
    # Generate an event in each tenant
    await async_client.post(
        "/auth/login",
        json={"email": admin_user_a["email"], "password": admin_user_a["password"]},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    await async_client.post(
        "/auth/login",
        json={"email": admin_user_b["email"], "password": admin_user_b["password"]},
        headers={"X-Tenant-Slug": SLUG_B},
    )

    # admin_user_a (ADMIN of tenant A) queries audit logs
    a_view = await _get_audit_logs(async_client, make_tenant_headers(admin_user_a), page_size=200)

    # All returned items must be scoped to tenant A
    for item in a_view["items"]:
        assert item["tenant_id"] == str(admin_user_a["tenant_id"]), (
            f"Expected tenant_id={admin_user_a['tenant_id']} but got {item['tenant_id']}"
        )

    # admin_user_b's login event specifically must not be in admin_a's view
    actor_ids_in_view = {item["actor_user_id"] for item in a_view["items"]}
    assert str(admin_user_b["id"]) not in actor_ids_in_view


async def test_super_admin_sees_all_logs(
    async_client, admin_user_a, admin_user_b, test_platform_user
):
    platform_headers = make_platform_headers(test_platform_user)

    # Generate a login event in each tenant
    await async_client.post(
        "/auth/login",
        json={"email": admin_user_a["email"], "password": admin_user_a["password"]},
        headers={"X-Tenant-Slug": SLUG_A},
    )
    await async_client.post(
        "/auth/login",
        json={"email": admin_user_b["email"], "password": admin_user_b["password"]},
        headers={"X-Tenant-Slug": SLUG_B},
    )

    # SUPER_ADMIN can see events for admin_user_a (tenant A)
    a_logs = await _get_audit_logs(
        async_client, platform_headers, actor_user_id=str(admin_user_a["id"])
    )
    assert a_logs["total"] >= 1

    # SUPER_ADMIN can see events for admin_user_b (tenant B)
    b_logs = await _get_audit_logs(
        async_client, platform_headers, actor_user_id=str(admin_user_b["id"])
    )
    assert b_logs["total"] >= 1

    # Filter by tenant A — all results must belong to tenant A
    a_only = await _get_audit_logs(
        async_client, platform_headers,
        tenant_id=str(admin_user_a["tenant_id"]),
        page_size=200,
    )
    for item in a_only["items"]:
        assert item["tenant_id"] == str(admin_user_a["tenant_id"])


# ---------------------------------------------------------------------------
# Tenant provisioning audit event
# ---------------------------------------------------------------------------


async def test_tenant_provisioned_writes_audit(async_client, test_platform_user):
    platform_headers = make_platform_headers(test_platform_user)
    unique_id = uuid.uuid4().hex[:8]
    tenant_name = f"Audit Org {unique_id}"
    admin_email = f"admin_{unique_id}@auditorg.com"

    resp = await async_client.post(
        "/tenants",
        headers=platform_headers,
        json={
            "name": tenant_name,
            "admin_email": admin_email,
            "admin_password": "Admin1234!",
            "admin_full_name": "Audit Admin",
        },
    )

    try:
        assert resp.status_code == 201
        tenant_data = resp.json()
        schema_name = tenant_data["schema_name"]
        tenant_id = tenant_data["id"]

        logs = await _get_audit_logs(
            async_client, platform_headers,
            event_type="TENANT_PROVISIONED",
            tenant_id=tenant_id,
        )
        assert logs["total"] >= 1
        entry = logs["items"][0]
        assert entry["schema_name"] == schema_name
        assert entry["actor_user_id"] == str(test_platform_user["id"])
    finally:
        async with _Session() as session:
            async with session.begin():
                schema_name = resp.json().get("schema_name") if resp.status_code == 201 else None
                if schema_name:
                    await session.execute(
                        text("DELETE FROM public.refresh_token_index WHERE schema_name = :s"),
                        {"s": schema_name},
                    )
                    await session.execute(
                        text("DELETE FROM public.tenants WHERE schema_name = :s"),
                        {"s": schema_name},
                    )
                    await session.execute(
                        text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
                    )


# ---------------------------------------------------------------------------
# Immutability enforcement
# ---------------------------------------------------------------------------


async def test_audit_logs_no_update_delete_api(async_client, test_platform_user):
    platform_headers = make_platform_headers(test_platform_user)
    fake_id = uuid.uuid4()

    r_patch = await async_client.patch(f"/audit-logs/{fake_id}", headers=platform_headers, json={})
    assert r_patch.status_code in (404, 405)

    r_delete = await async_client.delete(f"/audit-logs/{fake_id}", headers=platform_headers)
    assert r_delete.status_code in (404, 405)


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


async def test_faculty_cannot_access_audit_logs(async_client, test_tenant_a, faculty_user_a):
    resp = await async_client.get(
        "/audit-logs",
        headers=make_tenant_headers(faculty_user_a),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


async def test_pagination(async_client, test_tenant_a, admin_user_a, test_platform_user):
    platform_headers = make_platform_headers(test_platform_user)

    # Seed 5 login events for this specific user
    for _ in range(5):
        await async_client.post(
            "/auth/login",
            json={"email": admin_user_a["email"], "password": admin_user_a["password"]},
            headers={"X-Tenant-Slug": SLUG_A},
        )

    page1 = await _get_audit_logs(
        async_client, platform_headers,
        event_type="AUTH_LOGIN_SUCCESS",
        actor_user_id=str(admin_user_a["id"]),
        page=1,
        page_size=3,
    )
    assert page1["total"] >= 5
    assert len(page1["items"]) == 3

    page2 = await _get_audit_logs(
        async_client, platform_headers,
        event_type="AUTH_LOGIN_SUCCESS",
        actor_user_id=str(admin_user_a["id"]),
        page=2,
        page_size=3,
    )
    assert len(page2["items"]) >= 1

    # Pages must return different items
    ids_page1 = {item["id"] for item in page1["items"]}
    ids_page2 = {item["id"] for item in page2["items"]}
    assert ids_page1.isdisjoint(ids_page2)
