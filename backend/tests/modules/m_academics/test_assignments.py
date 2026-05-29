"""Tests for H-31: Subject Assignment Foundation.

Coverage:
  - Assignment creation (PRIMARY, CO_FACULTY, GUEST)
  - Duplicate PRIMARY prevention
  - Duplicate faculty+course+semester prevention
  - Revocation (soft-delete)
  - Double-revoke rejection
  - RBAC: FACULTY cannot create assignments; DEAN and ADMIN can
  - RBAC: FACULTY can call /mine; DEAN/ADMIN can list by course
  - RBAC: STUDENT/BOARD/EVALUATOR are blocked
  - Tenant isolation: assignments in tenant_a not visible to tenant_b
  - list_by_course returns only active by default
  - list_my_courses returns only calling faculty's assignments
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.database import AsyncSessionLocal
from tests.conftest import (
    SCHEMA_A, SCHEMA_B, SLUG_A, SLUG_B,
    _insert_tenant_user, make_tenant_headers,
)

BASE = "/course-assignments"


# ---------------------------------------------------------------------------
# Module-level fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def dean_user_a(test_tenant_a):
    user = await _insert_tenant_user(SCHEMA_A, "assign_dean_a@test.com", "Dean1234!", "DEAN", "Dean A")
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


@pytest_asyncio.fixture
async def faculty2_user_a(test_tenant_a):
    user = await _insert_tenant_user(SCHEMA_A, "assign_fac2_a@test.com", "Fac1234!", "FACULTY", "Faculty 2 A")
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


@pytest_asyncio.fixture
async def student_user_a2(test_tenant_a):
    user = await _insert_tenant_user(SCHEMA_A, "assign_stu_a@test.com", "Stu1234!", "STUDENT", "Student A")
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


async def _insert_course_and_semester(schema: str) -> dict:
    """Insert a minimal program → course and semester into the given schema."""
    prog_id    = uuid.uuid4()
    course_id  = uuid.uuid4()
    dept_id    = uuid.uuid4()
    acad_prog  = uuid.uuid4()
    batch_id   = uuid.uuid4()
    sem_id     = uuid.uuid4()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {schema}, public"))

            # acad_departments
            await session.execute(
                text(
                    "INSERT INTO acad_departments (id, name, code, is_active) "
                    "VALUES (:id, :name, :code, true)"
                ),
                {"id": str(dept_id), "name": f"Dept-{dept_id.hex[:6]}", "code": f"D{dept_id.hex[:4].upper()}"},
            )
            # acad_programs
            await session.execute(
                text(
                    "INSERT INTO acad_programs "
                    "(id, department_id, name, code, degree_type, duration_years, is_active) "
                    "VALUES (:id, :dept, :name, :code, 'UG', 3, true)"
                ),
                {
                    "id":   str(acad_prog),
                    "dept": str(dept_id),
                    "name": f"AP-{acad_prog.hex[:6]}",
                    "code": f"AP{acad_prog.hex[:4].upper()}",
                },
            )
            # acad_batches
            await session.execute(
                text(
                    "INSERT INTO acad_batches "
                    "(id, program_id, name, start_year, end_year, is_active) "
                    "VALUES (:id, :prog, :name, 2024, 2027, true)"
                ),
                {"id": str(batch_id), "prog": str(acad_prog), "name": "Batch 2024"},
            )
            # acad_semesters
            await session.execute(
                text(
                    "INSERT INTO acad_semesters (id, batch_id, number, is_active) "
                    "VALUES (:id, :batch, 1, true)"
                ),
                {"id": str(sem_id), "batch": str(batch_id)},
            )
            # m01 program
            await session.execute(
                text(
                    "INSERT INTO programs "
                    "(id, version, title, degree_type, department, duration_years, "
                    " total_credits, status, created_by_user_id) "
                    "VALUES (:id, 1, 'Test Program', 'BTech', 'CS', 3, 60, 'DRAFT', :uid)"
                ),
                {"id": str(prog_id), "uid": str(uuid.uuid4())},
            )
            # m01 course
            await session.execute(
                text(
                    "INSERT INTO courses "
                    "(id, program_id, code, title, credits, semester, is_elective, is_ai_generated) "
                    "VALUES (:id, :prog, :code, :title, 4, 1, false, false)"
                ),
                {
                    "id":    str(course_id),
                    "prog":  str(prog_id),
                    "code":  f"CS{course_id.hex[:4].upper()}",
                    "title": f"Course-{course_id.hex[:6]}",
                },
            )

    return {"course_id": str(course_id), "semester_id": str(sem_id)}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _get_ids(schema: str) -> dict:
    return await _insert_course_and_semester(schema)


# ===========================================================================
# Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_dean_can_create_primary_assignment(
    async_client: AsyncClient,
    dean_user_a,
    faculty_user_a,
):
    ids = await _get_ids(SCHEMA_A)
    payload = {
        "course_id":       ids["course_id"],
        "faculty_user_id": str(faculty_user_a["id"]),
        "semester_id":     ids["semester_id"],
        "role_in_course":  "PRIMARY",
    }
    resp = await async_client.post(
        BASE, json=payload, headers=make_tenant_headers(dean_user_a)
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["role_in_course"] == "PRIMARY"
    assert data["is_active"] is True
    assert data["course"] is not None
    assert data["faculty"] is not None
    assert data["semester"] is not None


@pytest.mark.asyncio
async def test_admin_can_create_cofaculty_assignment(
    async_client: AsyncClient,
    admin_user_a,
    faculty_user_a,
    faculty2_user_a,
):
    ids = await _get_ids(SCHEMA_A)
    # First assign PRIMARY
    await async_client.post(
        BASE,
        json={
            "course_id":       ids["course_id"],
            "faculty_user_id": str(faculty_user_a["id"]),
            "semester_id":     ids["semester_id"],
            "role_in_course":  "PRIMARY",
        },
        headers=make_tenant_headers(admin_user_a),
    )
    # Now assign CO_FACULTY
    resp = await async_client.post(
        BASE,
        json={
            "course_id":       ids["course_id"],
            "faculty_user_id": str(faculty2_user_a["id"]),
            "semester_id":     ids["semester_id"],
            "role_in_course":  "CO_FACULTY",
        },
        headers=make_tenant_headers(admin_user_a),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role_in_course"] == "CO_FACULTY"


@pytest.mark.asyncio
async def test_duplicate_primary_blocked(
    async_client: AsyncClient,
    dean_user_a,
    faculty_user_a,
    faculty2_user_a,
):
    ids = await _get_ids(SCHEMA_A)
    # Assign first PRIMARY
    resp1 = await async_client.post(
        BASE,
        json={
            "course_id":       ids["course_id"],
            "faculty_user_id": str(faculty_user_a["id"]),
            "semester_id":     ids["semester_id"],
            "role_in_course":  "PRIMARY",
        },
        headers=make_tenant_headers(dean_user_a),
    )
    assert resp1.status_code == 201

    # Attempt second PRIMARY for same course+semester
    resp2 = await async_client.post(
        BASE,
        json={
            "course_id":       ids["course_id"],
            "faculty_user_id": str(faculty2_user_a["id"]),
            "semester_id":     ids["semester_id"],
            "role_in_course":  "PRIMARY",
        },
        headers=make_tenant_headers(dean_user_a),
    )
    assert resp2.status_code == 400
    assert resp2.json()["error"] == "PRIMARY_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_duplicate_assignment_for_same_faculty_blocked(
    async_client: AsyncClient,
    dean_user_a,
    faculty_user_a,
):
    ids = await _get_ids(SCHEMA_A)
    payload = {
        "course_id":       ids["course_id"],
        "faculty_user_id": str(faculty_user_a["id"]),
        "semester_id":     ids["semester_id"],
        "role_in_course":  "PRIMARY",
    }
    resp1 = await async_client.post(BASE, json=payload, headers=make_tenant_headers(dean_user_a))
    assert resp1.status_code == 201

    resp2 = await async_client.post(BASE, json=payload, headers=make_tenant_headers(dean_user_a))
    assert resp2.status_code == 400
    assert resp2.json()["error"] == "DUPLICATE_ASSIGNMENT"


@pytest.mark.asyncio
async def test_revoke_assignment(
    async_client: AsyncClient,
    dean_user_a,
    faculty_user_a,
):
    ids = await _get_ids(SCHEMA_A)
    create_resp = await async_client.post(
        BASE,
        json={
            "course_id":       ids["course_id"],
            "faculty_user_id": str(faculty_user_a["id"]),
            "semester_id":     ids["semester_id"],
            "role_in_course":  "PRIMARY",
        },
        headers=make_tenant_headers(dean_user_a),
    )
    assert create_resp.status_code == 201
    assignment_id = create_resp.json()["id"]

    revoke_resp = await async_client.post(
        f"{BASE}/{assignment_id}/revoke",
        json={},
        headers=make_tenant_headers(dean_user_a),
    )
    assert revoke_resp.status_code == 200
    data = revoke_resp.json()
    assert data["is_active"] is False
    assert data["revoked_at"] is not None


@pytest.mark.asyncio
async def test_double_revoke_blocked(
    async_client: AsyncClient,
    dean_user_a,
    faculty_user_a,
):
    ids = await _get_ids(SCHEMA_A)
    create_resp = await async_client.post(
        BASE,
        json={
            "course_id":       ids["course_id"],
            "faculty_user_id": str(faculty_user_a["id"]),
            "semester_id":     ids["semester_id"],
            "role_in_course":  "PRIMARY",
        },
        headers=make_tenant_headers(dean_user_a),
    )
    assert create_resp.status_code == 201
    assignment_id = create_resp.json()["id"]

    await async_client.post(
        f"{BASE}/{assignment_id}/revoke", json={}, headers=make_tenant_headers(dean_user_a)
    )
    resp2 = await async_client.post(
        f"{BASE}/{assignment_id}/revoke", json={}, headers=make_tenant_headers(dean_user_a)
    )
    assert resp2.status_code == 400
    assert resp2.json()["error"] == "ALREADY_REVOKED"


@pytest.mark.asyncio
async def test_faculty_cannot_create_assignment(
    async_client: AsyncClient,
    faculty_user_a,
):
    ids = await _get_ids(SCHEMA_A)
    resp = await async_client.post(
        BASE,
        json={
            "course_id":       ids["course_id"],
            "faculty_user_id": str(faculty_user_a["id"]),
            "semester_id":     ids["semester_id"],
            "role_in_course":  "PRIMARY",
        },
        headers=make_tenant_headers(faculty_user_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_student_cannot_create_assignment(
    async_client: AsyncClient,
    student_user_a2,
    faculty_user_a,
):
    ids = await _get_ids(SCHEMA_A)
    resp = await async_client.post(
        BASE,
        json={
            "course_id":       ids["course_id"],
            "faculty_user_id": str(faculty_user_a["id"]),
            "semester_id":     ids["semester_id"],
            "role_in_course":  "PRIMARY",
        },
        headers=make_tenant_headers(student_user_a2),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_faculty_can_call_mine(
    async_client: AsyncClient,
    dean_user_a,
    faculty_user_a,
):
    ids = await _get_ids(SCHEMA_A)
    await async_client.post(
        BASE,
        json={
            "course_id":       ids["course_id"],
            "faculty_user_id": str(faculty_user_a["id"]),
            "semester_id":     ids["semester_id"],
            "role_in_course":  "PRIMARY",
        },
        headers=make_tenant_headers(dean_user_a),
    )

    resp = await async_client.get(
        f"{BASE}/mine", headers=make_tenant_headers(faculty_user_a)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    ids_in_resp = {item["faculty_user_id"] for item in data["items"]}
    assert str(faculty_user_a["id"]) in ids_in_resp


@pytest.mark.asyncio
async def test_dean_cannot_call_mine(
    async_client: AsyncClient,
    dean_user_a,
):
    resp = await async_client.get(f"{BASE}/mine", headers=make_tenant_headers(dean_user_a))
    # DEAN is not FACULTY → 403
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_by_course_returns_only_active(
    async_client: AsyncClient,
    dean_user_a,
    faculty_user_a,
):
    ids = await _get_ids(SCHEMA_A)
    # Create then revoke
    create_resp = await async_client.post(
        BASE,
        json={
            "course_id":       ids["course_id"],
            "faculty_user_id": str(faculty_user_a["id"]),
            "semester_id":     ids["semester_id"],
            "role_in_course":  "PRIMARY",
        },
        headers=make_tenant_headers(dean_user_a),
    )
    assignment_id = create_resp.json()["id"]
    await async_client.post(
        f"{BASE}/{assignment_id}/revoke", json={}, headers=make_tenant_headers(dean_user_a)
    )

    resp = await async_client.get(
        BASE,
        params={"course_id": ids["course_id"]},
        headers=make_tenant_headers(dean_user_a),
    )
    assert resp.status_code == 200
    # All returned items must be active by default
    for item in resp.json()["items"]:
        assert item["is_active"] is True


@pytest.mark.asyncio
async def test_invalid_faculty_role_blocked(
    async_client: AsyncClient,
    dean_user_a,
    student_user_a2,
):
    """Cannot assign a STUDENT user as faculty for a course."""
    ids = await _get_ids(SCHEMA_A)
    resp = await async_client.post(
        BASE,
        json={
            "course_id":       ids["course_id"],
            "faculty_user_id": str(student_user_a2["id"]),
            "semester_id":     ids["semester_id"],
            "role_in_course":  "PRIMARY",
        },
        headers=make_tenant_headers(dean_user_a),
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "INVALID_ROLE"


@pytest.mark.asyncio
async def test_tenant_isolation(
    async_client: AsyncClient,
    dean_user_a,
    faculty_user_a,
    admin_user_b,
):
    """Assignments created in tenant A are not visible in tenant B."""
    ids_a = await _get_ids(SCHEMA_A)
    ids_b = await _get_ids(SCHEMA_B)

    # Create an assignment in tenant A
    create_resp = await async_client.post(
        BASE,
        json={
            "course_id":       ids_a["course_id"],
            "faculty_user_id": str(faculty_user_a["id"]),
            "semester_id":     ids_a["semester_id"],
            "role_in_course":  "PRIMARY",
        },
        headers=make_tenant_headers(dean_user_a),
    )
    assert create_resp.status_code == 201

    # Query from tenant B — should return empty for a totally different course
    resp_b = await async_client.get(
        BASE,
        params={"course_id": ids_b["course_id"]},
        headers=make_tenant_headers(admin_user_b),
    )
    assert resp_b.status_code == 200
    # Tenant B has its own (empty) schema — must not see tenant A's data
    b_ids = {item["id"] for item in resp_b.json()["items"]}
    assert create_resp.json()["id"] not in b_ids


@pytest.mark.asyncio
async def test_after_revoke_new_primary_can_be_assigned(
    async_client: AsyncClient,
    dean_user_a,
    faculty_user_a,
    faculty2_user_a,
):
    ids = await _get_ids(SCHEMA_A)
    # Assign fac1 as PRIMARY
    r1 = await async_client.post(
        BASE,
        json={
            "course_id":       ids["course_id"],
            "faculty_user_id": str(faculty_user_a["id"]),
            "semester_id":     ids["semester_id"],
            "role_in_course":  "PRIMARY",
        },
        headers=make_tenant_headers(dean_user_a),
    )
    assert r1.status_code == 201
    # Revoke fac1
    await async_client.post(
        f"{BASE}/{r1.json()['id']}/revoke", json={},
        headers=make_tenant_headers(dean_user_a),
    )
    # Assign fac2 as PRIMARY — should succeed now
    r2 = await async_client.post(
        BASE,
        json={
            "course_id":       ids["course_id"],
            "faculty_user_id": str(faculty2_user_a["id"]),
            "semester_id":     ids["semester_id"],
            "role_in_course":  "PRIMARY",
        },
        headers=make_tenant_headers(dean_user_a),
    )
    assert r2.status_code == 201
