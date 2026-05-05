from datetime import timedelta

from app.core.auth.security import create_access_token
from tests.conftest import make_tenant_headers, make_platform_headers


async def test_faculty_can_access_me(async_client, test_tenant_a, faculty_user_a):
    headers = make_tenant_headers(faculty_user_a)
    resp = await async_client.get("/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == faculty_user_a["email"]


async def test_faculty_cannot_create_user(async_client, test_tenant_a, faculty_user_a):
    headers = make_tenant_headers(faculty_user_a)
    resp = await async_client.post(
        "/admin/users",
        json={
            "email": "new@test.com",
            "password": "Password1234!",
            "full_name": "New User",
            "role": "STUDENT",
        },
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "FORBIDDEN"


async def test_admin_can_create_user(async_client, test_tenant_a, admin_user_a):
    headers = make_tenant_headers(admin_user_a)
    resp = await async_client.post(
        "/admin/users",
        json={
            "email": "created@test.com",
            "password": "Password1234!",
            "full_name": "Created User",
            "role": "FACULTY",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "created@test.com"
    assert resp.json()["role"] == "FACULTY"


async def test_no_token_on_protected_route(async_client, test_tenant_a):
    resp = await async_client.get("/auth/me")
    assert resp.status_code == 422  # Authorization header missing → FastAPI 422


async def test_expired_token_rejected(async_client, test_tenant_a, faculty_user_a):
    expired_token = create_access_token(
        {
            "sub": str(faculty_user_a["id"]),
            "tenant_id": str(faculty_user_a["tenant_id"]),
            "schema_name": faculty_user_a["schema_name"],
            "role": faculty_user_a["role"],
            "email": faculty_user_a["email"],
        },
        expires_delta=timedelta(seconds=-1),
    )
    resp = await async_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert resp.status_code == 401


async def test_admin_cannot_create_super_admin(async_client, test_tenant_a, admin_user_a):
    headers = make_tenant_headers(admin_user_a)
    resp = await async_client.post(
        "/admin/users",
        json={
            "email": "super@test.com",
            "password": "Password1234!",
            "full_name": "Would Be Super",
            "role": "SUPER_ADMIN",
        },
        headers=headers,
    )
    assert resp.status_code == 422


async def test_super_admin_on_tenant_me_returns_403(async_client, test_platform_user):
    headers = make_platform_headers(test_platform_user)
    resp = await async_client.get("/auth/me", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "FORBIDDEN"
