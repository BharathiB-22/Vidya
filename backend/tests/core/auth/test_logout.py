from tests.conftest import SLUG_A, make_tenant_headers


async def _login(async_client, user):
    resp = await async_client.post(
        "/auth/login",
        json={"email": user["email"], "password": user["password"]},
        headers={"X-Tenant-Slug": user["slug"]},
    )
    assert resp.status_code == 200
    return resp.json()


async def test_logout_revokes_token(async_client, test_tenant_a, admin_user_a):
    tokens = await _login(async_client, admin_user_a)
    headers = make_tenant_headers(admin_user_a)

    resp = await async_client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=headers,
    )
    assert resp.status_code == 200

    # Subsequent refresh with the same token must fail
    resp2 = await async_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp2.status_code == 401


async def test_logout_all_scoped_to_user(async_client, test_tenant_a, admin_user_a, faculty_user_a):
    admin_tokens = await _login(async_client, admin_user_a)
    faculty_tokens = await _login(async_client, faculty_user_a)

    admin_headers = make_tenant_headers(admin_user_a)
    resp = await async_client.post("/auth/logout-all", headers=admin_headers)
    assert resp.status_code == 200

    # Admin's own token must be revoked
    r1 = await async_client.post(
        "/auth/refresh", json={"refresh_token": admin_tokens["refresh_token"]}
    )
    assert r1.status_code == 401

    # Faculty token in same tenant must still work
    r2 = await async_client.post(
        "/auth/refresh", json={"refresh_token": faculty_tokens["refresh_token"]}
    )
    assert r2.status_code == 200


async def test_logout_idempotent(async_client, test_tenant_a, admin_user_a):
    tokens = await _login(async_client, admin_user_a)
    headers = make_tenant_headers(admin_user_a)
    body = {"refresh_token": tokens["refresh_token"]}

    r1 = await async_client.post("/auth/logout", json=body, headers=headers)
    assert r1.status_code == 200

    r2 = await async_client.post("/auth/logout", json=body, headers=headers)
    assert r2.status_code == 200
