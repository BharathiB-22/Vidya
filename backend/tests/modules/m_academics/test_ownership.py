"""Tests for the Faculty Responsibilities hierarchy fix (Phase 2 refinements).

Verifies that each course in `course_assignments` resolves its own
program/department strictly through Course -> Semester -> Batch -> Program
-> Department, so a course can never be paired with an unrelated
department/program elsewhere on the page.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.database import AsyncSessionLocal
from tests.conftest import SCHEMA_A, SLUG_A, _insert_tenant_user, make_tenant_headers
from tests.modules.m_academics.test_assignments import _insert_course_and_semester

BASE = "/academics"


@pytest_asyncio.fixture
async def faculty_user_ownership_a(test_tenant_a):
    user = await _insert_tenant_user(SCHEMA_A, "ownership_fac_a@test.com", "Fac1234!", "FACULTY", "Faculty Ownership A")
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


async def _assign_faculty_to_course(faculty_user_id: str, course_id: str, semester_id: str) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            await session.execute(
                text(
                    "INSERT INTO subject_assignments "
                    "(id, course_id, faculty_user_id, semester_id, role_in_course, "
                    " is_active, assigned_by_user_id, assigned_at) "
                    "VALUES (:id, :cid, :fid, :sid, 'PRIMARY', true, :fid, now())"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "cid": course_id,
                    "fid": str(faculty_user_id),
                    "sid": semester_id,
                },
            )


@pytest.mark.asyncio
async def test_course_resolves_its_own_program_and_department(
    async_client: AsyncClient,
    faculty_user_ownership_a,
):
    """Two courses under two different (program, department) pairs must each
    report their OWN program/department — never a mix-and-match."""
    ids_1 = await _insert_course_and_semester(SCHEMA_A)
    ids_2 = await _insert_course_and_semester(SCHEMA_A)

    await _assign_faculty_to_course(
        faculty_user_ownership_a["id"], ids_1["course_id"], ids_1["semester_id"]
    )
    await _assign_faculty_to_course(
        faculty_user_ownership_a["id"], ids_2["course_id"], ids_2["semester_id"]
    )

    resp = await async_client.get(
        f"{BASE}/faculty/me/responsibilities",
        headers=make_tenant_headers(faculty_user_ownership_a),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    courses_by_id = {c["course_id"]: c for c in data["course_assignments"]}
    c1 = courses_by_id[ids_1["course_id"]]
    c2 = courses_by_id[ids_2["course_id"]]

    # Each course's acad_program_id is unique per _insert_course_and_semester call,
    # so their resolved program_id must differ and must be non-null.
    assert c1["program_id"] is not None
    assert c2["program_id"] is not None
    assert c1["program_id"] != c2["program_id"]
    assert c1["program_id"] == ids_1["acad_program_id"]
    assert c2["program_id"] == ids_2["acad_program_id"]
    assert c1["department_id"] is not None
    assert c2["department_id"] is not None
