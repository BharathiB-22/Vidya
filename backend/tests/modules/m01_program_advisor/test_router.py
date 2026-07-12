"""
Router / RBAC integration tests for M01 programs endpoints.
Uses async_client against a real tenant schema.
"""
from __future__ import annotations

import uuid

from tests.conftest import make_tenant_headers
from tests.modules.m01_program_advisor.conftest import (
    approve_all_syllabi_committed,
    bind_to_batch_committed,
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
    """Add 3 outcomes + 12 courses (4 sems × 3 × 5 credits = 60) that satisfy MSc
    rules, and bind the curriculum to a batch so it can be submitted."""
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
    await bind_to_batch_committed(uuid.UUID(program_id))


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


async def test_faculty_cannot_approve_curriculum(async_client, test_tenant_a, admin_user_a, faculty_user_a):
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)

    faculty_h = make_tenant_headers(faculty_user_a)
    resp = await async_client.post(
        f"/governance/programs/{program['id']}/approve", json={}, headers=faculty_h,
    )
    assert resp.status_code == 403


async def test_dean_cannot_approve_curriculum(async_client, test_tenant_a, admin_user_a, dean_user_a):
    """The central rule of Phase A: the Dean prepares curriculum and can never
    approve it. There is no Dean-facing approve endpoint, and the governance
    endpoint rejects a DEAN outright."""
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)
    await force_status_committed(uuid.UUID(program["id"]), ProgramStatus.PENDING_APPROVAL)

    dean_h = make_tenant_headers(dean_user_a)
    resp = await async_client.post(
        f"/governance/programs/{program['id']}/approve", json={}, headers=dean_h,
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "NOT_GOVERNANCE"

    # And the old Dean approve route is gone for good.
    legacy = await async_client.post(f"{BASE}/{program['id']}/approve", json={}, headers=dean_h)
    assert legacy.status_code == 404


async def test_unauthenticated_returns_401(async_client, test_tenant_a):
    # No Authorization header. `get_current_user` takes only optional header
    # params, so FastAPI calls it before the missing X-Tenant-Slug can be raised
    # as a 422 — and it rejects the request outright. 401 is the right answer for
    # "no credentials"; the old assertion of 422 described the wrong dependency.
    resp = await async_client.get(BASE)
    assert resp.status_code == 401


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

async def test_dean_submits_then_governance_approves_and_locks(
    async_client, test_tenant_a, admin_user_a, dean_user_a, board_user_a,
):
    """The whole Phase A happy path, end to end over HTTP:
    Dean prepares → Dean submits → Board writes the syllabus → Board approves and
    locks → Dean publishes."""
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    board_h = make_tenant_headers(board_user_a)

    program = await _create_program(async_client, admin_h)
    await _build_compliant_via_api(async_client, admin_h, program["id"])

    submitted = await async_client.post(
        f"{BASE}/{program['id']}/submit", json={"note": "Ready"}, headers=dean_h,
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "PENDING_APPROVAL"

    # The Board's readiness worksheet: nothing has a syllabus yet, so the
    # curriculum cannot be approved.
    readiness = await async_client.get(
        f"/governance/programs/{program['id']}/readiness", headers=board_h,
    )
    assert readiness.status_code == 200
    assert readiness.json()["can_approve"] is False
    assert readiness.json()["missing_count"] == readiness.json()["total_subjects"]

    await approve_all_syllabi_committed(uuid.UUID(program["id"]), board_user_a["id"])

    approved = await async_client.post(
        f"/governance/programs/{program['id']}/approve",
        json={"comment": "Approved by BoS"},
        headers=board_h,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    published = await async_client.post(f"{BASE}/{program['id']}/publish", json={}, headers=dean_h)
    assert published.status_code == 200
    assert published.json()["status"] == "PUBLISHED"


async def test_approve_is_refused_until_every_subject_has_a_syllabus(
    async_client, test_tenant_a, admin_user_a, dean_user_a, board_user_a,
):
    """The gate, over HTTP. Approval is permanent, so a subject locked with no
    official syllabus could never be given one."""
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    board_h = make_tenant_headers(board_user_a)

    program = await _create_program(async_client, admin_h)
    await _build_compliant_via_api(async_client, admin_h, program["id"])
    await async_client.post(f"{BASE}/{program['id']}/submit", json={}, headers=dean_h)

    resp = await async_client.post(
        f"/governance/programs/{program['id']}/approve", json={}, headers=board_h,
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "SYLLABUS_INCOMPLETE"


async def test_submit_requires_draft(async_client, test_tenant_a, admin_user_a, dean_user_a):
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)
    await _build_compliant_via_api(async_client, admin_h, program["id"])
    await force_status_committed(uuid.UUID(program["id"]), ProgramStatus.APPROVED)

    dean_h = make_tenant_headers(dean_user_a)
    resp = await async_client.post(f"{BASE}/{program['id']}/submit", json={}, headers=dean_h)
    assert resp.status_code == 409
    assert resp.json()["error"] == "INVALID_STATUS"


async def test_submit_non_compliant_curriculum_returns_422(
    async_client, test_tenant_a, admin_user_a, dean_user_a,
):
    # No courses, no outcomes. The Board must never be handed this.
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)

    dean_h = make_tenant_headers(dean_user_a)
    resp = await async_client.post(f"{BASE}/{program['id']}/submit", json={}, headers=dean_h)
    assert resp.status_code == 422
    assert resp.json()["error"] == "COMPLIANCE_FAILED"


async def test_there_is_no_return_or_reject_endpoint(
    async_client, test_tenant_a, admin_user_a, dean_user_a, board_user_a,
):
    """The Board is the academic authority: it enhances the curriculum rather
    than handing it back. Work never returns to the Dean, so the routes that used
    to do that are gone — not merely hidden from the UI."""
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    board_h = make_tenant_headers(board_user_a)

    program = await _create_program(async_client, admin_h)
    await _build_compliant_via_api(async_client, admin_h, program["id"])
    await async_client.post(f"{BASE}/{program['id']}/submit", json={}, headers=dean_h)

    for url in (
        f"/governance/programs/{program['id']}/return",
        f"{BASE}/{program['id']}/reject",
    ):
        resp = await async_client.post(url, json={"comment": "x", "reason": "x"}, headers=board_h)
        assert resp.status_code == 404, url


async def test_dean_cannot_edit_curriculum_under_review(
    async_client, test_tenant_a, admin_user_a, dean_user_a,
):
    """Once submitted, the curriculum belongs to the governance authority. The
    Dean is read-only on it — enforced on the API, not just hidden in the UI."""
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)

    program = await _create_program(async_client, admin_h)
    await _build_compliant_via_api(async_client, admin_h, program["id"])
    await async_client.post(f"{BASE}/{program['id']}/submit", json={}, headers=dean_h)

    resp = await async_client.patch(
        f"{BASE}/{program['id']}", json={"title": "Sneaky edit"}, headers=dean_h,
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "AWAITING_GOVERNANCE"

    course = await async_client.post(
        f"{BASE}/{program['id']}/courses",
        json={"code": "CS998", "title": "Sneaky", "credits": 4, "semester": 1, "is_elective": False},
        headers=dean_h,
    )
    assert course.status_code == 403


async def test_governance_can_edit_curriculum_under_review(
    async_client, test_tenant_a, admin_user_a, dean_user_a, board_user_a,
):
    """The mirror image: governance CAN revise credits/structure while it holds
    the curriculum. That is what "Board can modify" means."""
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    board_h = make_tenant_headers(board_user_a)

    program = await _create_program(async_client, admin_h)
    await _build_compliant_via_api(async_client, admin_h, program["id"])
    await async_client.post(f"{BASE}/{program['id']}/submit", json={}, headers=dean_h)

    resp = await async_client.patch(
        f"{BASE}/{program['id']}", json={"title": "Board Revised"}, headers=board_h,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Board Revised"


async def test_curriculum_is_locked_after_approval(
    async_client, test_tenant_a, admin_user_a, dean_user_a, board_user_a,
):
    """Approval freezes it for EVERYONE — the Dean, the Admin, and the very Board
    that just approved it. A change means a new version."""
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    board_h = make_tenant_headers(board_user_a)

    program = await _create_program(async_client, admin_h)
    await _build_compliant_via_api(async_client, admin_h, program["id"])
    await async_client.post(f"{BASE}/{program['id']}/submit", json={}, headers=dean_h)
    await approve_all_syllabi_committed(uuid.UUID(program["id"]), board_user_a["id"])
    await async_client.post(
        f"/governance/programs/{program['id']}/approve", json={}, headers=board_h,
    )

    for headers in (dean_h, board_h, admin_h):
        resp = await async_client.patch(
            f"{BASE}/{program['id']}", json={"title": "Locked"}, headers=headers,
        )
        assert resp.status_code == 409
        assert resp.json()["error"] == "CURRICULUM_LOCKED"


# ---------------------------------------------------------------------------
# Immutability via API
# ---------------------------------------------------------------------------

async def test_update_approved_program_blocked(async_client, test_tenant_a, admin_user_a):
    # Phase A: approval LOCKS the curriculum. It is no longer editable, by anyone.
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)
    await force_status_committed(uuid.UUID(program["id"]), ProgramStatus.APPROVED)

    resp = await async_client.patch(
        f"{BASE}/{program['id']}", json={"title": "Not Editable"}, headers=admin_h
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "CURRICULUM_LOCKED"


async def test_update_published_program_blocked(async_client, test_tenant_a, admin_user_a):
    admin_h = make_tenant_headers(admin_user_a)
    program = await _create_program(async_client, admin_h)
    await force_status_committed(uuid.UUID(program["id"]), ProgramStatus.PUBLISHED)

    resp = await async_client.patch(
        f"{BASE}/{program['id']}", json={"title": "Blocked"}, headers=admin_h
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "CURRICULUM_LOCKED"


async def test_publish_keeps_it_locked(async_client, test_tenant_a, admin_user_a, dean_user_a):
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
    assert blocked.json()["error"] == "CURRICULUM_LOCKED"


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
