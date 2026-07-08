"""
Router / RBAC integration tests for M01 programs endpoints.
Uses async_client against a real tenant schema.
"""
from __future__ import annotations

import uuid

from tests.conftest import make_tenant_headers
from tests.modules.m01_program_advisor.conftest import (
    force_status_committed,
    make_program_payload,
)
from app.modules.m01_program_advisor.models import ProgramStatus

BASE = "/programs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_program(async_client, headers) -> dict:
    resp = await async_client.post(BASE, json=make_program_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _add_outcome(async_client, headers, program_id: str, code: str) -> None:
    resp = await async_client.post(
        f"{BASE}/{program_id}/outcomes",
        json={"code": code, "description": f"Outcome {code}"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


async def _add_course(
    async_client, headers, program_id: str, code: str, semester: int, is_elective: bool = False
) -> None:
    resp = await async_client.post(
        f"{BASE}/{program_id}/courses",
        json={
            "code": code,
            "title": f"Course {code}",
            "credits": 5,
            "semester": semester,
            "is_elective": is_elective,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


async def _build_compliant_via_api(async_client, headers, program_id: str) -> None:
    """Add 3 outcomes + 12 courses (4 sems × 3 × 5 credits = 60) that satisfy MSc rules."""
    for i in range(1, 4):
        await _add_outcome(async_client, headers, program_id, f"PO{i}")
    idx = 1
    for sem in range(1, 5):
        for _ in range(3):
            await _add_course(
                async_client, headers, program_id,
                code=f"CS{idx:03d}", semester=sem,
                is_elective=(idx in (3, 6)),
            )
            idx += 1


# ---------------------------------------------------------------------------
# RBAC — FACULTY blocked from write endpoints
# ---------------------------------------------------------------------------

async def test_faculty_cannot_create_program(async_client, test_tenant_a, faculty_user_a):
    headers = make_tenant_headers(faculty_user_a)
    resp = await async_client.post(BASE, json=make_program_payload(), headers=headers)
    assert resp.status_code == 403


async def test_faculty_cannot_update_program(async_client, test_tenant_a, admin_user_a, faculty_user_a):
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)

    faculty_h = make_tenant_headers(faculty_user_a)
    resp = await async_client.patch(
        f"{BASE}/{program['id']}", json={"title": "Changed"}, headers=faculty_h
    )
    assert resp.status_code == 403


async def test_faculty_cannot_delete_program(async_client, test_tenant_a, admin_user_a, faculty_user_a):
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)

    faculty_h = make_tenant_headers(faculty_user_a)
    resp = await async_client.delete(f"{BASE}/{program['id']}", headers=faculty_h)
    assert resp.status_code == 403


async def test_faculty_cannot_approve_program(async_client, test_tenant_a, admin_user_a, faculty_user_a):
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)

    faculty_h = make_tenant_headers(faculty_user_a)
    resp = await async_client.post(f"{BASE}/{program['id']}/approve", json={}, headers=faculty_h)
    assert resp.status_code == 403


async def test_admin_cannot_approve_program(async_client, test_tenant_a, admin_user_a):
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)

    resp = await async_client.post(f"{BASE}/{program['id']}/approve", json={}, headers=admin_h)
    assert resp.status_code == 403


async def test_unauthenticated_returns_422(async_client, test_tenant_a):
    resp = await async_client.get(BASE)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Program CRUD
# ---------------------------------------------------------------------------

async def test_create_program_success(async_client, test_tenant_a, admin_user_a):
    headers = make_tenant_headers(admin_user_a)
    resp = await async_client.post(BASE, json=make_program_payload(), headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "DRAFT"
    assert data["version"] == 1
    assert "id" in data


async def test_get_program_success(async_client, test_tenant_a, admin_user_a, faculty_user_a):
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)

    faculty_h = make_tenant_headers(faculty_user_a)
    resp = await async_client.get(f"{BASE}/{program['id']}", headers=faculty_h)
    assert resp.status_code == 200
    assert resp.json()["id"] == program["id"]


async def test_get_program_not_found(async_client, test_tenant_a, faculty_user_a):
    headers = make_tenant_headers(faculty_user_a)
    resp = await async_client.get(f"{BASE}/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


async def test_update_program_success(async_client, test_tenant_a, admin_user_a):
    headers = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, headers)

    resp = await async_client.patch(
        f"{BASE}/{program['id']}", json={"title": "Updated Title"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"


async def test_delete_program_success(async_client, test_tenant_a, admin_user_a):
    headers = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, headers)

    resp = await async_client.delete(f"{BASE}/{program['id']}", headers=headers)
    assert resp.status_code == 200

    resp = await async_client.get(f"{BASE}/{program['id']}", headers=headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# List + filter
# ---------------------------------------------------------------------------

async def test_list_programs_filtered_by_status(async_client, test_tenant_a, admin_user_a):
    headers = make_tenant_headers(admin_user_a)
    await _create_program(async_client, headers)
    await _create_program(async_client, headers)

    resp = await async_client.get(f"{BASE}?status=DRAFT", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    for item in data["items"]:
        assert item["status"] == "DRAFT"


# ---------------------------------------------------------------------------
# Course and outcome creation
# ---------------------------------------------------------------------------

async def test_add_course_success(async_client, test_tenant_a, admin_user_a):
    headers = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, headers)

    resp = await async_client.post(
        f"{BASE}/{program['id']}/courses",
        json={"code": "CS001", "title": "Intro", "credits": 4, "semester": 1, "is_elective": False},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["code"] == "CS001"


async def test_add_outcome_success(async_client, test_tenant_a, admin_user_a):
    headers = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, headers)

    resp = await async_client.post(
        f"{BASE}/{program['id']}/outcomes",
        json={"code": "PO1", "description": "Graduates can apply knowledge"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["code"] == "PO1"


# ---------------------------------------------------------------------------
# Compliance endpoint
# ---------------------------------------------------------------------------

async def test_compliance_check_endpoint(async_client, test_tenant_a, admin_user_a):
    headers = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, headers)

    resp = await async_client.get(f"{BASE}/{program['id']}/compliance", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "passed" in data
    assert "violations" in data


# ---------------------------------------------------------------------------
# State transitions via API
# ---------------------------------------------------------------------------

async def test_approve_requires_pending_approval_status(async_client, test_tenant_a, admin_user_a, dean_user_a):
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)

    dean_h = make_tenant_headers(dean_user_a)
    resp = await async_client.post(f"{BASE}/{program['id']}/approve", json={}, headers=dean_h)
    assert resp.status_code == 409
    assert resp.json()["error"] == "INVALID_STATUS"


async def test_dean_can_approve_pending_program(async_client, test_tenant_a, admin_user_a, dean_user_a):
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)
    await _build_compliant_via_api(async_client, admin_h, program["id"])
    await force_status_committed(uuid.UUID(program["id"]), ProgramStatus.PENDING_APPROVAL)

    dean_h = make_tenant_headers(dean_user_a)
    resp = await async_client.post(f"{BASE}/{program['id']}/approve", json={}, headers=dean_h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"


async def test_approve_non_compliant_program_returns_422(async_client, test_tenant_a, admin_user_a, dean_user_a):
    # A freshly created DRAFT program (no courses, no outcomes) forced to PENDING_APPROVAL
    # must fail compliance and return 422 COMPLIANCE_FAILED, not silently succeed.
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)
    await force_status_committed(uuid.UUID(program["id"]), ProgramStatus.PENDING_APPROVAL)

    dean_h = make_tenant_headers(dean_user_a)
    resp = await async_client.post(f"{BASE}/{program['id']}/approve", json={}, headers=dean_h)
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "COMPLIANCE_FAILED"
    assert body["message"]  # non-empty compliance violation string


async def test_dean_can_reject_pending_program(async_client, test_tenant_a, admin_user_a, dean_user_a):
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)
    await force_status_committed(uuid.UUID(program["id"]), ProgramStatus.PENDING_APPROVAL)

    dean_h = make_tenant_headers(dean_user_a)
    resp = await async_client.post(
        f"{BASE}/{program['id']}/reject", json={"reason": "Needs revision"}, headers=dean_h
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "DRAFT"


# ---------------------------------------------------------------------------
# Immutability via API
# ---------------------------------------------------------------------------

async def test_update_approved_program_allowed(async_client, test_tenant_a, admin_user_a):
    # Phase 4.2: Approved programs remain editable/deletable until Published.
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)
    await force_status_committed(uuid.UUID(program["id"]), ProgramStatus.APPROVED)

    resp = await async_client.patch(
        f"{BASE}/{program['id']}", json={"title": "Still Editable"}, headers=admin_h
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Still Editable"


async def test_update_published_program_blocked(async_client, test_tenant_a, admin_user_a):
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)
    await force_status_committed(uuid.UUID(program["id"]), ProgramStatus.PUBLISHED)

    resp = await async_client.patch(
        f"{BASE}/{program['id']}", json={"title": "Blocked"}, headers=admin_h
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "INVALID_STATUS"


async def test_publish_program_locks_it(async_client, test_tenant_a, admin_user_a, dean_user_a):
    admin_h = make_tenant_headers(admin_user_a)
    dean_h = make_tenant_headers(dean_user_a)
    program = await _create_program(async_client, admin_h)
    await force_status_committed(uuid.UUID(program["id"]), ProgramStatus.APPROVED)

    resp = await async_client.post(f"{BASE}/{program['id']}/publish", json={}, headers=dean_h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "PUBLISHED"

    blocked = await async_client.patch(
        f"{BASE}/{program['id']}", json={"title": "Blocked"}, headers=admin_h
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"] == "INVALID_STATUS"


async def test_add_course_to_approved_blocked(async_client, test_tenant_a, admin_user_a):
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)
    await force_status_committed(uuid.UUID(program["id"]), ProgramStatus.APPROVED)

    resp = await async_client.post(
        f"{BASE}/{program['id']}/courses",
        json={"code": "CS999", "title": "Blocked", "credits": 4, "semester": 1, "is_elective": False},
        headers=admin_h,
    )
    assert resp.status_code == 409


async def test_fork_approved_program(async_client, test_tenant_a, admin_user_a):
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)
    await force_status_committed(uuid.UUID(program["id"]), ProgramStatus.APPROVED)

    resp = await async_client.post(f"{BASE}/{program['id']}/fork", headers=admin_h)
    assert resp.status_code == 201
    forked = resp.json()
    assert forked["version"] == 2
    assert forked["parent_version_id"] == program["id"]
    assert forked["status"] == "DRAFT"
