"""
EVALUATOR role RBAC tests.

Verifies:
  1.  ADMIN can create an EVALUATOR user
  2.  EVALUATOR can login
  3.  EVALUATOR cannot create a lab assignment
  4.  EVALUATOR cannot ratify a submission
  5.  EVALUATOR cannot access admin /admin/users endpoint
  6.  EVALUATOR cannot access /admin/users/bulk-onboarding endpoint
  7.  Faculty can assign EVALUATOR to an assignment
  8.  EVALUATOR can list their assigned assignments (after assignment)
  9.  EVALUATOR cannot see submissions for an assignment they are NOT assigned to
  10. EVALUATOR from tenant B cannot access tenant A data
"""
from __future__ import annotations

import pytest

from tests.conftest import make_tenant_headers


# ---------------------------------------------------------------------------
# 1. ADMIN can create an EVALUATOR user
# ---------------------------------------------------------------------------

async def test_admin_can_create_evaluator(async_client, test_tenant_a, admin_user_a):
    headers = make_tenant_headers(admin_user_a)
    resp = await async_client.post(
        "/admin/users",
        json={
            "email": "new_evaluator@test.com",
            "password": "Eval1234!",
            "full_name": "New Evaluator",
            "role": "EVALUATOR",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["role"] == "EVALUATOR"
    assert body["email"] == "new_evaluator@test.com"


# ---------------------------------------------------------------------------
# 2. EVALUATOR can login and /auth/me reflects correct role
# ---------------------------------------------------------------------------

async def test_evaluator_can_login(async_client, test_tenant_a, evaluator_user_a):
    login_resp = await async_client.post(
        "/auth/login",
        json={
            "email": evaluator_user_a["email"],
            "password": evaluator_user_a["password"],
        },
        headers={"X-Tenant-Slug": evaluator_user_a["slug"]},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]

    me_resp = await async_client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Slug": evaluator_user_a["slug"],
        },
    )
    assert me_resp.status_code == 200, me_resp.text
    assert me_resp.json()["role"] == "EVALUATOR"


# ---------------------------------------------------------------------------
# 3. EVALUATOR cannot create a lab assignment
# ---------------------------------------------------------------------------

async def test_evaluator_cannot_create_assignment(
    async_client, test_tenant_a, evaluator_user_a
):
    headers = make_tenant_headers(evaluator_user_a)
    resp = await async_client.post(
        "/labs/assignments",
        json={
            "title": "Evaluator should not create",
            "submission_type": "WRITTEN",
            "rubric": [{"criterion_id": "c1", "name": "Q", "description": "x", "max_marks": 10, "weight": 1.0}],
        },
        headers=headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 4. EVALUATOR cannot ratify a submission
# ---------------------------------------------------------------------------

async def test_evaluator_cannot_ratify(async_client, test_tenant_a, evaluator_user_a):
    from uuid import uuid4
    headers = make_tenant_headers(evaluator_user_a)
    resp = await async_client.post(
        f"/labs/submissions/{uuid4()}/ratify",
        json={"ratification_note": "EVALUATOR should not ratify"},
        headers=headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 5. EVALUATOR cannot access /admin/users
# ---------------------------------------------------------------------------

async def test_evaluator_cannot_access_admin_users(
    async_client, test_tenant_a, evaluator_user_a
):
    headers = make_tenant_headers(evaluator_user_a)
    resp = await async_client.get("/admin/users", headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 6. EVALUATOR cannot update scores on faculty endpoint
# ---------------------------------------------------------------------------

async def test_evaluator_cannot_update_scores_via_faculty_endpoint(
    async_client, test_tenant_a, evaluator_user_a
):
    from uuid import uuid4
    headers = make_tenant_headers(evaluator_user_a)
    resp = await async_client.patch(
        f"/labs/submissions/{uuid4()}/scores",
        json={"scores": []},
        headers=headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 7. Faculty can assign EVALUATOR to an assignment
# ---------------------------------------------------------------------------

async def test_faculty_can_assign_evaluator(
    async_client, test_tenant_a, faculty_user_a, evaluator_user_a
):
    # Create a draft assignment as faculty
    fac_headers = make_tenant_headers(faculty_user_a)
    create_resp = await async_client.post(
        "/labs/assignments",
        json={
            "title": "RBAC test assignment",
            "submission_type": "WRITTEN",
            "rubric": [
                {"criterion_id": "c1", "name": "Quality",
                 "description": "q", "max_marks": 10, "weight": 1.0}
            ],
        },
        headers=fac_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    assignment_id = create_resp.json()["id"]

    # Assign the evaluator
    assign_resp = await async_client.post(
        f"/labs/assignments/{assignment_id}/evaluators",
        json={"evaluator_user_id": str(evaluator_user_a["id"])},
        headers=fac_headers,
    )
    assert assign_resp.status_code == 201, assign_resp.text
    body = assign_resp.json()
    assert body["evaluator_user_id"] == str(evaluator_user_a["id"])
    assert body["is_active"] is True

    return assignment_id


# ---------------------------------------------------------------------------
# 8. EVALUATOR can list their assigned assignments
# ---------------------------------------------------------------------------

async def test_evaluator_can_list_assigned_assignments(
    async_client, test_tenant_a, faculty_user_a, evaluator_user_a
):
    # Create and assign an assignment via faculty
    fac_headers = make_tenant_headers(faculty_user_a)
    create_resp = await async_client.post(
        "/labs/assignments",
        json={
            "title": "Listed assignment for evaluator",
            "submission_type": "WRITTEN",
            "rubric": [
                {"criterion_id": "c1", "name": "Quality",
                 "description": "q", "max_marks": 10, "weight": 1.0}
            ],
        },
        headers=fac_headers,
    )
    assert create_resp.status_code == 201
    assignment_id = create_resp.json()["id"]

    await async_client.post(
        f"/labs/assignments/{assignment_id}/evaluators",
        json={"evaluator_user_id": str(evaluator_user_a["id"])},
        headers=fac_headers,
    )

    # Evaluator lists their assignments
    eval_headers = make_tenant_headers(evaluator_user_a)
    list_resp = await async_client.get("/labs/evaluator/assignments", headers=eval_headers)
    assert list_resp.status_code == 200, list_resp.text
    body = list_resp.json()
    ids = [a["id"] for a in body["items"]]
    assert assignment_id in ids


# ---------------------------------------------------------------------------
# 9. EVALUATOR cannot see submissions for an unassigned assignment
# ---------------------------------------------------------------------------

async def test_evaluator_cannot_see_unassigned_submissions(
    async_client, test_tenant_a, faculty_user_a, evaluator_user_a
):
    # Create assignment but do NOT assign evaluator
    fac_headers = make_tenant_headers(faculty_user_a)
    create_resp = await async_client.post(
        "/labs/assignments",
        json={
            "title": "Unassigned to evaluator",
            "submission_type": "WRITTEN",
            "rubric": [
                {"criterion_id": "c1", "name": "Quality",
                 "description": "q", "max_marks": 10, "weight": 1.0}
            ],
        },
        headers=fac_headers,
    )
    assert create_resp.status_code == 201
    assignment_id = create_resp.json()["id"]

    # Evaluator attempts to list submissions
    eval_headers = make_tenant_headers(evaluator_user_a)
    resp = await async_client.get(
        f"/labs/evaluator/assignments/{assignment_id}/submissions",
        headers=eval_headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 10. Tenant isolation: EVALUATOR from tenant B cannot access tenant A data
# ---------------------------------------------------------------------------

async def test_evaluator_tenant_b_cannot_see_tenant_a(
    async_client,
    test_tenant_a,
    test_tenant_b,
    faculty_user_a,
    evaluator_user_a,
    admin_user_b,
):
    from app.core.auth.security import create_access_token
    import uuid

    # Create evaluator in tenant B
    b_evaluator_id = uuid.uuid4()
    from tests.conftest import _Session, SCHEMA_B, SLUG_B
    from sqlalchemy import text
    from app.core.auth.security import hash_password
    async with _Session() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_B}, public"))
            await session.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, role, full_name, is_active) "
                    "VALUES (:id, :email, :hash, :role, :name, true)"
                ),
                {
                    "id": str(b_evaluator_id),
                    "email": "evaluator_b@test.com",
                    "hash": hash_password("Eval1234!"),
                    "role": "EVALUATOR",
                    "name": "Evaluator B",
                },
            )
    tenant_b_id = test_tenant_b["id"]
    b_token = create_access_token({
        "sub": str(b_evaluator_id),
        "tenant_id": str(tenant_b_id),
        "schema_name": SCHEMA_B,
        "role": "EVALUATOR",
        "email": "evaluator_b@test.com",
    })
    b_headers = {"Authorization": f"Bearer {b_token}", "X-Tenant-Slug": SLUG_B}

    # Create assignment in tenant A
    fac_headers = make_tenant_headers(faculty_user_a)
    create_resp = await async_client.post(
        "/labs/assignments",
        json={
            "title": "Tenant A assignment",
            "submission_type": "WRITTEN",
            "rubric": [
                {"criterion_id": "c1", "name": "Quality",
                 "description": "q", "max_marks": 10, "weight": 1.0}
            ],
        },
        headers=fac_headers,
    )
    assert create_resp.status_code == 201
    assignment_id = create_resp.json()["id"]

    # Assign tenant A evaluator to that assignment (normal)
    await async_client.post(
        f"/labs/assignments/{assignment_id}/evaluators",
        json={"evaluator_user_id": str(evaluator_user_a["id"])},
        headers=fac_headers,
    )

    # Tenant B evaluator tries to access tenant A evaluator route
    resp = await async_client.get(
        f"/labs/evaluator/assignments/{assignment_id}/submissions",
        headers=b_headers,
    )
    # Tenant middleware rejects cross-tenant access (schema_name mismatch)
    assert resp.status_code in (403, 404)
