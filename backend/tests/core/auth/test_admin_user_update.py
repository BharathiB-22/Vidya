"""Tests for ADMIN PATCH /admin/users/{user_id}.

Covers:
- ADMIN can update a GUIDE user's identifier
- ADMIN can update full_name, role, is_active for any tenant user
- Non-ADMIN roles (FACULTY, STUDENT, GUIDE) are blocked with 403
"""
import uuid

from tests.conftest import make_tenant_headers


async def test_admin_can_update_guide_identifier(
    async_client, test_tenant_a, admin_user_a, guide_user_a
):
    """ADMIN can set/update identifier on a GUIDE user."""
    headers = make_tenant_headers(admin_user_a)
    resp = await async_client.patch(
        f"/admin/users/{guide_user_a['id']}",
        json={"identifier": "RGABC01"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["identifier"] == "RGABC01"
    assert body["role"] == "GUIDE"


async def test_admin_can_update_user_full_name(
    async_client, test_tenant_a, admin_user_a, faculty_user_a
):
    """ADMIN can update full_name of any tenant user."""
    headers = make_tenant_headers(admin_user_a)
    resp = await async_client.patch(
        f"/admin/users/{faculty_user_a['id']}",
        json={"full_name": "Updated Faculty"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["full_name"] == "Updated Faculty"


async def test_admin_can_change_user_role(
    async_client, test_tenant_a, admin_user_a, faculty_user_a
):
    """ADMIN can change a user's role."""
    headers = make_tenant_headers(admin_user_a)
    resp = await async_client.patch(
        f"/admin/users/{faculty_user_a['id']}",
        json={"role": "DEAN"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "DEAN"


async def test_admin_can_deactivate_user(
    async_client, test_tenant_a, admin_user_a, student_user_a
):
    """ADMIN can set is_active=False on a user."""
    headers = make_tenant_headers(admin_user_a)
    resp = await async_client.patch(
        f"/admin/users/{student_user_a['id']}",
        json={"is_active": False},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False


async def test_admin_update_nonexistent_user_returns_404(
    async_client, test_tenant_a, admin_user_a
):
    """ADMIN patching a user_id that doesn't exist → 404."""
    headers = make_tenant_headers(admin_user_a)
    resp = await async_client.patch(
        f"/admin/users/{uuid.uuid4()}",
        json={"full_name": "Ghost"},
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "USER_NOT_FOUND"


async def test_admin_update_no_fields_returns_422(
    async_client, test_tenant_a, admin_user_a, faculty_user_a
):
    """PATCH with an empty body (no fields to update) → 422 NO_FIELDS."""
    headers = make_tenant_headers(admin_user_a)
    resp = await async_client.patch(
        f"/admin/users/{faculty_user_a['id']}",
        json={},
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "NO_FIELDS"


async def test_faculty_cannot_update_user(
    async_client, test_tenant_a, faculty_user_a, student_user_a
):
    """FACULTY is not ADMIN → PATCH /admin/users/{id} returns 403."""
    headers = make_tenant_headers(faculty_user_a)
    resp = await async_client.patch(
        f"/admin/users/{student_user_a['id']}",
        json={"full_name": "Hacked Name"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_student_cannot_update_user(
    async_client, test_tenant_a, student_user_a, faculty_user_a
):
    """STUDENT is not ADMIN → PATCH /admin/users/{id} returns 403."""
    headers = make_tenant_headers(student_user_a)
    resp = await async_client.patch(
        f"/admin/users/{faculty_user_a['id']}",
        json={"full_name": "Hacked Name"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"


async def test_guide_cannot_update_user(
    async_client, test_tenant_a, guide_user_a, faculty_user_a
):
    """GUIDE is not ADMIN → PATCH /admin/users/{id} returns 403."""
    headers = make_tenant_headers(guide_user_a)
    resp = await async_client.patch(
        f"/admin/users/{faculty_user_a['id']}",
        json={"full_name": "Hacked Name"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "FORBIDDEN"
