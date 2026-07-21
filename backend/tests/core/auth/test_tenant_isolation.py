from tests.conftest import SCHEMA_A, SCHEMA_B, make_tenant_headers


async def test_me_returns_correct_tenant_data(async_client, test_tenant_a, faculty_user_a):
    headers = make_tenant_headers(faculty_user_a)
    resp = await async_client.get("/auth/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == faculty_user_a["email"]
    assert data["schema_name"] == SCHEMA_A


async def test_admin_users_scoped_to_own_schema(
    async_client, test_tenant_a, test_tenant_b, admin_user_a, admin_user_b, faculty_user_a
):
    headers_a = make_tenant_headers(admin_user_a)
    resp = await async_client.get("/admin/users", headers=headers_a)
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]

    # Users from tenant A present
    assert admin_user_a["email"] in emails
    assert faculty_user_a["email"] in emails

    # Users from tenant B not present
    assert admin_user_b["email"] not in emails


async def test_forged_jwt_rejected(async_client, test_tenant_a, faculty_user_a):
    # Build a JWT with a wrong secret — signature invalid
    from jose import jwt as jose_jwt
    forged = jose_jwt.encode(
        {
            "sub": str(faculty_user_a["id"]),
            "schema_name": SCHEMA_A,
            "role": "ADMIN",
            "email": faculty_user_a["email"],
        },
        "wrong-secret",
        algorithm="HS256",
    )
    resp = await async_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {forged}"}
    )
    assert resp.status_code == 401


async def test_created_user_in_correct_schema(
    async_client, test_tenant_a, test_tenant_b, admin_user_a, admin_user_b
):
    headers_a = make_tenant_headers(admin_user_a)
    resp = await async_client.post(
        "/admin/users",
        json={
            "email": "isolation_check@test.com",
            "password": "Password1234!",
            "full_name": "Isolation Test",
            "role": "FACULTY",
        },
        headers=headers_a,
    )
    assert resp.status_code == 201

    # Visible in tenant A
    users_a = await async_client.get("/admin/users", headers=headers_a)
    emails_a = [u["email"] for u in users_a.json()]
    assert "isolation_check@test.com" in emails_a

    # Not visible in tenant B
    headers_b = make_tenant_headers(admin_user_b)
    users_b = await async_client.get("/admin/users", headers=headers_b)
    emails_b = [u["email"] for u in users_b.json()]
    assert "isolation_check@test.com" not in emails_b


async def test_cross_tenant_jwt_cannot_see_other_schema(
    async_client, test_tenant_a, test_tenant_b, faculty_user_b, admin_user_a
):
    # faculty_b's JWT is locked to schema_b — GET /auth/me returns their own data
    headers_b = make_tenant_headers(faculty_user_b)
    resp = await async_client.get("/auth/me", headers=headers_b)
    assert resp.status_code == 200
    assert resp.json()["schema_name"] == SCHEMA_B

    # admin_a cannot see faculty_b in their own user list
    headers_a = make_tenant_headers(admin_user_a)
    users_a = await async_client.get("/admin/users", headers=headers_a)
    emails_a = [u["email"] for u in users_a.json()]
    assert faculty_user_b["email"] not in emails_a
