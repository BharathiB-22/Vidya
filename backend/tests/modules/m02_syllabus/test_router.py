"""
Router RBAC and HTTP integration tests for M02 /syllabi endpoints.
Uses async_client against a real tenant schema.
"""
from __future__ import annotations

import uuid

import pytest

from tests.conftest import make_tenant_headers
from tests.modules.m02_syllabus.conftest import (
    build_compliant_syllabus,
    force_syllabus_status_committed,
    make_syllabus_payload,
)
from app.modules.m02_syllabus.models import SyllabusStatus
from app.modules.m02_syllabus.schemas import (
    CourseOutcomeCreate,
    BloomLevel,
    SyllabusCreate,
    SyllabusUnitCreate,
    UnitTopicItem,
)
from app.database import AsyncSessionLocal
from sqlalchemy import text

BASE = "/syllabi"


# ---------------------------------------------------------------------------
# Helper: create syllabus via API
# ---------------------------------------------------------------------------

async def _create_syllabus(async_client, headers, course_id: uuid.UUID) -> dict:
    resp = await async_client.post(
        BASE, json=make_syllabus_payload(course_id), headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _assign_faculty_to_course(
    course_id: uuid.UUID,
    faculty_user_id: uuid.UUID,
    schema_name: str,
) -> None:
    """Seed a minimal SubjectAssignment chain (dept→program→batch→semester→assignment)
    so that faculty passes the H-33 assignment gate when creating/listing syllabi."""
    dep_id  = uuid.uuid4()
    prog_id = uuid.uuid4()
    bat_id  = uuid.uuid4()
    sem_id  = uuid.uuid4()
    suffix  = str(dep_id)[:8]  # 8 hex chars from UUID prefix

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {schema_name}, public"))
            await session.execute(text(
                "INSERT INTO acad_departments (id, name, code, is_active) "
                "VALUES (:id, :name, :code, true)"
            ), {"id": str(dep_id), "name": f"Dept {suffix}", "code": f"D{suffix[:7]}"})
            await session.execute(text(
                "INSERT INTO acad_programs "
                "(id, department_id, name, code, degree_type, duration_years, is_active) "
                "VALUES (:id, :dep, :name, :code, 'UG', 4, true)"
            ), {"id": str(prog_id), "dep": str(dep_id), "name": "B.Tech Test", "code": f"P{suffix[:7]}"})
            await session.execute(text(
                "INSERT INTO acad_batches (id, program_id, name, start_year, end_year, is_active) "
                "VALUES (:id, :prog, :name, 2024, 2028, true)"
            ), {"id": str(bat_id), "prog": str(prog_id), "name": "Batch 2024"})
            await session.execute(text(
                "INSERT INTO acad_semesters (id, batch_id, number, is_active) "
                "VALUES (:id, :bat, 1, true)"
            ), {"id": str(sem_id), "bat": str(bat_id)})
            await session.execute(text(
                "INSERT INTO subject_assignments "
                "(id, course_id, faculty_user_id, semester_id, assigned_by_user_id, is_active, role_in_course) "
                "VALUES (:id, :course, :faculty, :sem, :by, true, 'PRIMARY')"
            ), {
                "id":      str(uuid.uuid4()),
                "course":  str(course_id),
                "faculty": str(faculty_user_id),
                "sem":     str(sem_id),
                "by":      str(uuid.uuid4()),
            })


async def _build_compliant_via_db(syllabus_id: uuid.UUID, schema_name: str) -> None:
    """Seed compliant syllabus data directly in DB (bypasses HTTP — used for state-setup)."""
    from app.modules.m02_syllabus.models import BloomLevel as BL, SyllabusUnit, CourseOutcome
    from app.modules.m02_syllabus.schemas import (
        CourseOutcomeCreate, SyllabusUnitCreate, UnitTopicItem,
    )
    from app.modules.m02_syllabus.service import SyllabusService

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {schema_name}, public"))

        bloom_levels = [BL.REMEMBER, BL.APPLY, BL.EVALUATE, BL.CREATE]
        for i, bl in enumerate(bloom_levels, 1):
            await SyllabusService.add_co(
                syllabus_id,
                CourseOutcomeCreate(
                    code=f"CO{i}",
                    description=f"Course outcome {i} with sufficient description",
                    bloom_level=bl,
                    display_order=i,
                ),
                caller_role="BOARD", db=session,
            )

        for i in range(1, 5):
            await SyllabusService.add_unit(
                syllabus_id,
                SyllabusUnitCreate(
                    unit_number=i, title=f"Unit {i} topic area",
                    total_hours=12, topics=[UnitTopicItem(title="T")],
                ),
                caller_role="BOARD", db=session,
            )
        await session.commit()


# ===========================================================================
# RBAC — Phase A (Academic Governance V1)
#
# The syllabus is curriculum, and curriculum belongs to the governance authority.
#   Governance  writes it, generates it, approves it, locks it.
#   Faculty     TEACH to it — they read it and never write it.
#   Dean        reads it.
# ===========================================================================

async def test_dean_cannot_create_syllabus(async_client, test_tenant_a, dean_user_a):
    headers = make_tenant_headers(dean_user_a)
    resp = await async_client.post(
        BASE, json={"course_id": str(uuid.uuid4())}, headers=headers
    )
    assert resp.status_code == 403


async def test_dean_can_read_syllabus_list(async_client, test_tenant_a, admin_user_a, dean_user_a, m01_setup):
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)

    await _create_syllabus(async_client, admin_h, m01_setup["course_id"])

    resp = await async_client.get(
        BASE, params={"course_id": str(m01_setup["course_id"])}, headers=dean_h
    )
    assert resp.status_code == 200


async def test_faculty_cannot_write_syllabus(async_client, test_tenant_a, faculty_user_a, m01_setup):
    """The core m02 change in Phase A: Faculty no longer author syllabi, even for
    a course they are assigned to. They build course kits and lesson plans UNDER
    the approved syllabus instead."""
    await _assign_faculty_to_course(
        m01_setup["course_id"], faculty_user_a["id"], test_tenant_a["schema_name"]
    )
    headers = make_tenant_headers(faculty_user_a)
    resp = await async_client.post(
        BASE, json=make_syllabus_payload(m01_setup["course_id"]), headers=headers
    )
    assert resp.status_code == 403


async def test_faculty_can_read_syllabus(async_client, test_tenant_a, admin_user_a, faculty_user_a, m01_setup):
    # Faculty read the syllabus of a course they teach — they must, in order to
    # teach to it. They simply cannot change it. (Faculty reads stay scoped to
    # assigned courses, so seed the assignment.)
    await _assign_faculty_to_course(
        m01_setup["course_id"], faculty_user_a["id"], test_tenant_a["schema_name"]
    )
    admin_h   = make_tenant_headers(admin_user_a)
    faculty_h = make_tenant_headers(faculty_user_a)

    await _create_syllabus(async_client, admin_h, m01_setup["course_id"])

    resp = await async_client.get(
        BASE, params={"course_id": str(m01_setup["course_id"])}, headers=faculty_h
    )
    assert resp.status_code == 200


async def test_governance_can_create_syllabus(async_client, test_tenant_a, board_user_a, m01_setup):
    headers = make_tenant_headers(board_user_a)
    resp = await async_client.post(
        BASE, json=make_syllabus_payload(m01_setup["course_id"]), headers=headers
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "DRAFT"


async def test_student_cannot_read_syllabus(async_client, test_tenant_a, student_user_a, m01_setup):
    headers = make_tenant_headers(student_user_a)
    resp = await async_client.get(
        BASE, params={"course_id": str(m01_setup["course_id"])}, headers=headers
    )
    assert resp.status_code == 403


async def test_dean_cannot_approve_syllabus(async_client, test_tenant_a, admin_user_a, dean_user_a, m01_setup):
    admin_h = make_tenant_headers(admin_user_a)
    dean_h  = make_tenant_headers(dean_user_a)
    data    = await _create_syllabus(async_client, admin_h, m01_setup["course_id"])

    await _build_compliant_via_db(uuid.UUID(data["id"]), test_tenant_a["schema_name"])

    # The Dean used to approve syllabi. The syllabus is curriculum, and the
    # curriculum belongs to the Board — the Dean only reads it.
    resp = await async_client.post(f"{BASE}/{data['id']}/approve", json={}, headers=dean_h)
    assert resp.status_code == 403


async def test_governance_can_approve_syllabus(
    async_client, test_tenant_a, admin_user_a, board_user_a, m01_setup,
):
    """DRAFT -> APPROVED in one step. There is no submit-for-review: the Board
    writes the syllabus and the Board signs it off, so there is nobody to hand it
    to in between."""
    admin_h = make_tenant_headers(admin_user_a)
    board_h = make_tenant_headers(board_user_a)
    data    = await _create_syllabus(async_client, admin_h, m01_setup["course_id"])

    await _build_compliant_via_db(uuid.UUID(data["id"]), test_tenant_a["schema_name"])

    resp = await async_client.post(f"{BASE}/{data['id']}/approve", json={}, headers=board_h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"


async def test_faculty_cannot_write_a_syllabus(
    async_client, test_tenant_a, admin_user_a, faculty_user_a, m01_setup,
):
    """Faculty never author or edit the official syllabus. They teach to it and
    build lesson plans, PPTs, course kits and assignments underneath it."""
    admin_h   = make_tenant_headers(admin_user_a)
    faculty_h = make_tenant_headers(faculty_user_a)
    data = await _create_syllabus(async_client, admin_h, m01_setup["course_id"])

    create = await async_client.post(
        BASE, json={"course_id": str(m01_setup["course_id"])}, headers=faculty_h,
    )
    assert create.status_code == 403

    edit = await async_client.patch(
        f"{BASE}/{data['id']}", json={"custom_instructions": "Mine now"}, headers=faculty_h,
    )
    assert edit.status_code == 403

    approve = await async_client.post(f"{BASE}/{data['id']}/approve", json={}, headers=faculty_h)
    assert approve.status_code == 403


async def test_syllabus_lock_and_unlock_endpoints_are_gone(
    async_client, test_tenant_a, admin_user_a, board_user_a, m01_setup,
):
    """A syllabus is locked by CURRICULUM APPROVAL, not on its own — structure and
    syllabus freeze together or the pair is incoherent — and it is never unlocked.
    Both routes are deleted, not merely hidden."""
    admin_h = make_tenant_headers(admin_user_a)
    board_h = make_tenant_headers(board_user_a)
    data = await _create_syllabus(async_client, admin_h, m01_setup["course_id"])

    for action in ("lock", "unlock"):
        resp = await async_client.post(
            f"{BASE}/{data['id']}/{action}", json={}, headers=board_h,
        )
        assert resp.status_code == 404, action


# ===========================================================================
# HTTP error mapping
# ===========================================================================

async def test_404_on_unknown_syllabus_id(async_client, test_tenant_a, admin_user_a):
    headers = make_tenant_headers(admin_user_a)
    resp = await async_client.get(f"{BASE}/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body
    assert "message" in body


async def test_409_when_approving_non_draft(async_client, test_tenant_a, admin_user_a, board_user_a, m01_setup):
    admin_h = make_tenant_headers(admin_user_a)
    board_h = make_tenant_headers(board_user_a)
    data    = await _create_syllabus(async_client, admin_h, m01_setup["course_id"])

    await _build_compliant_via_db(uuid.UUID(data["id"]), test_tenant_a["schema_name"])
    resp = await async_client.post(f"{BASE}/{data['id']}/approve", json={}, headers=board_h)
    assert resp.status_code == 200

    # Try to approve again — should be 409
    resp2 = await async_client.post(f"{BASE}/{data['id']}/approve", json={}, headers=board_h)
    assert resp2.status_code == 409
    body = resp2.json()
    assert body.get("error") == "INVALID_STATUS"


async def test_422_when_approving_non_compliant_syllabus(
    async_client, test_tenant_a, admin_user_a, board_user_a, m01_setup
):
    """The Board cannot sign off a syllabus with no outcomes and no units,
    however it came to be that way."""
    admin_h = make_tenant_headers(admin_user_a)
    board_h = make_tenant_headers(board_user_a)
    data    = await _create_syllabus(async_client, admin_h, m01_setup["course_id"])

    resp = await async_client.post(f"{BASE}/{data['id']}/approve", json={}, headers=board_h)
    assert resp.status_code == 422
    assert resp.json().get("error") == "COMPLIANCE_FAILED"


async def test_editing_an_approved_syllabus_returns_it_to_draft(
    async_client, test_tenant_a, admin_user_a, board_user_a, m01_setup
):
    """Approval is a sign-off, not a freeze. The Board may change its mind right
    up to curriculum approval — but a sign-off has to mean "I have read exactly
    this", so it cannot survive an edit to the thing it signed off on."""
    admin_h = make_tenant_headers(admin_user_a)
    board_h = make_tenant_headers(board_user_a)
    data    = await _create_syllabus(async_client, admin_h, m01_setup["course_id"])
    sid     = uuid.UUID(data["id"])

    await _build_compliant_via_db(sid, test_tenant_a["schema_name"])
    resp = await async_client.post(f"{BASE}/{data['id']}/approve", json={}, headers=board_h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"

    resp2 = await async_client.patch(
        f"{BASE}/{data['id']}", json={"custom_instructions": "Changed"}, headers=board_h
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "DRAFT"
    assert resp2.json()["approved_at"] is None


async def test_409_when_editing_a_locked_syllabus(
    async_client, test_tenant_a, admin_user_a, board_user_a, m01_setup
):
    """LOCKED is the one truly immutable state: the curriculum was approved, so
    nobody edits — not the Board that locked it, not an Admin."""
    admin_h = make_tenant_headers(admin_user_a)
    board_h = make_tenant_headers(board_user_a)
    data    = await _create_syllabus(async_client, admin_h, m01_setup["course_id"])
    sid     = uuid.UUID(data["id"])

    await force_syllabus_status_committed(sid, SyllabusStatus.LOCKED)

    for headers in (board_h, admin_h):
        resp = await async_client.patch(
            f"{BASE}/{data['id']}", json={"custom_instructions": "Changed"}, headers=headers
        )
        assert resp.status_code == 409
        assert resp.json().get("error") == "CURRICULUM_LOCKED"


async def test_error_detail_always_has_error_and_message_keys(
    async_client, test_tenant_a, admin_user_a, board_user_a, m01_setup
):
    admin_h = make_tenant_headers(admin_user_a)
    board_h = make_tenant_headers(board_user_a)
    data    = await _create_syllabus(async_client, admin_h, m01_setup["course_id"])

    # Approving an empty syllabus → 422 COMPLIANCE_FAILED
    resp = await async_client.post(f"{BASE}/{data['id']}/approve", json={}, headers=board_h)
    assert resp.status_code == 422
    body = resp.json()
    assert "error"   in body, f"Missing 'error' key in {body}"
    assert "message" in body, f"Missing 'message' key in {body}"


# ===========================================================================
# Endpoint registration spot checks
# ===========================================================================

async def test_list_syllabi_without_course_id_returns_all(async_client, test_tenant_a, admin_user_a):
    headers = make_tenant_headers(admin_user_a)
    resp = await async_client.get(BASE, headers=headers)
    # course_id is optional; omitting it lists all syllabuses in the tenant
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body


async def test_get_compliance_returns_structured_response(
    async_client, test_tenant_a, admin_user_a, m01_setup
):
    headers = make_tenant_headers(admin_user_a)
    data    = await _create_syllabus(async_client, headers, m01_setup["course_id"])

    resp = await async_client.get(f"{BASE}/{data['id']}/compliance", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "passed"     in body
    assert "violations" in body
    assert body["passed"] is False  # empty syllabus


async def test_fork_returns_201_and_new_version(
    async_client, test_tenant_a, admin_user_a, m01_setup
):
    headers = make_tenant_headers(admin_user_a)
    data    = await _create_syllabus(async_client, headers, m01_setup["course_id"])

    resp = await async_client.post(
        f"{BASE}/{data['id']}/fork",
        json={"change_note": "Exploring new approach"},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["version"] == 2
    assert body["status"]  == "DRAFT"


async def test_the_faculty_syllabus_workflow_endpoints_are_gone(
    async_client, test_tenant_a, admin_user_a, board_user_a, m01_setup
):
    """submit-for-review / resubmit / reject / request-revision / dean-overview all
    belonged to the workflow where FACULTY authored a syllabus and a DEAN reviewed
    it. One body now writes it and signs it off, so a handoff between two parties
    has nothing to mean. Deleted, not hidden — a removed workflow left in the tree
    is how it comes back."""
    admin_h = make_tenant_headers(admin_user_a)
    board_h = make_tenant_headers(board_user_a)
    data    = await _create_syllabus(async_client, admin_h, m01_setup["course_id"])

    for action in ("submit-for-review", "resubmit", "reject", "request-revision"):
        resp = await async_client.post(
            f"{BASE}/{data['id']}/{action}",
            json={"reason": "x", "comments": "x"},
            headers=board_h,
        )
        assert resp.status_code == 404, action

    # /dean-overview is unrouted, so it now falls through to GET /syllabi/{id} and
    # fails UUID parsing (422) rather than 404-ing. Either way it is not an
    # endpoint; what matters is that it no longer returns a Dean review dashboard.
    overview = await async_client.get(f"{BASE}/dean-overview", headers=board_h)
    assert overview.status_code in (404, 422)


# ===========================================================================
# Tenant isolation
# ===========================================================================

async def test_syllabus_not_visible_across_tenants(
    async_client, test_tenant_a, test_tenant_b,
    admin_user_a, admin_user_b, m01_setup
):
    """A syllabus created in tenant A must not be readable by tenant B."""
    headers_a = make_tenant_headers(admin_user_a)
    headers_b = make_tenant_headers(admin_user_b)

    data = await _create_syllabus(async_client, headers_a, m01_setup["course_id"])

    # Tenant B tries to access tenant A's syllabus ID
    resp = await async_client.get(f"{BASE}/{data['id']}", headers=headers_b)
    assert resp.status_code == 404, (
        f"Tenant B must not see tenant A's syllabus; got {resp.status_code}"
    )
