"""Faculty ↔ Program assignment tests — ERP Onboarding Phase 1 / Step 3.

Integration tests against a real PostgreSQL tenant schema.  They build a small
academic structure (school → dept → 2 programs), create FACULTY users, then
exercise assign / revoke / reactivate / list and verify soft-delete semantics.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.auth.security import hash_password
from app.core.onboarding.faculty_program_service import (
    FacultyProgramService,
    FacultyProgramServiceError,
)

_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"statement_cache_size": 0},
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

_PW = hash_password("Faculty@123")


async def _setup_structure(schema: str) -> dict:
    """Create SCA school, CA dept, MCA + BCA programs."""
    ids = {k: uuid.uuid4() for k in ("school", "dept", "mca", "bca")}
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            await s.execute(text(
                "INSERT INTO sis_schools (id, code, name, is_active) "
                "VALUES (:id, 'SCA', 'School of Computing', true)"
            ), {"id": str(ids["school"])})
            await s.execute(text(
                "INSERT INTO acad_departments (id, school_id, name, code, is_active) "
                "VALUES (:id, :sch, 'Computer Applications', 'CA', true)"
            ), {"id": str(ids["dept"]), "sch": str(ids["school"])})
            for prog, code, deg in (("mca", "MCA", "PG"), ("bca", "BCA", "UG")):
                await s.execute(text(
                    "INSERT INTO acad_programs "
                    "(id, department_id, name, code, degree_type, duration_years, is_active) "
                    "VALUES (:id, :dept, :name, :code, :deg, 3, true)"
                ), {"id": str(ids[prog]), "dept": str(ids["dept"]),
                    "name": f"Program {code}", "code": code, "deg": deg})
    return ids


async def _make_user(schema: str, name: str, role: str = "FACULTY") -> uuid.UUID:
    uid = uuid.uuid4()
    email = f"{name.lower().replace(' ', '.')}.{uid.hex[:6]}@test.edu"
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            await s.execute(text(
                "INSERT INTO users (id, email, password_hash, role, full_name, is_active) "
                "VALUES (:id, :email, :pw, :role, :name, true)"
            ), {"id": str(uid), "email": email, "pw": _PW, "role": role, "name": name})
    return uid


# --- service runners (mirror the _admin_db session.begin() boundary) --------

async def _assign(schema, faculty, program, actor):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await FacultyProgramService.assign_program(
                s, faculty_user_id=faculty, program_id=program, assigned_by=actor,
            )


async def _revoke(schema, faculty, program, actor):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await FacultyProgramService.revoke_program(
                s, faculty_user_id=faculty, program_id=program, revoked_by=actor,
            )


async def _list_programs(schema, faculty, include_inactive=False):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await FacultyProgramService.list_programs(
                s, faculty_user_id=faculty, include_inactive=include_inactive,
            )


async def _list_faculty(schema, program, include_inactive=False):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await FacultyProgramService.list_faculty_for_program(
                s, program_id=program, include_inactive=include_inactive,
            )


async def _row_count(schema, faculty, program) -> tuple[int, int]:
    """Return (total_rows, active_rows) for a (faculty, program) pair."""
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            r = await s.execute(text(
                "SELECT count(*) AS total, count(*) FILTER (WHERE is_active) AS active "
                "FROM faculty_program_assignments "
                "WHERE faculty_user_id = :f AND program_id = :p"
            ), {"f": str(faculty), "p": str(program)})
            m = r.mappings().one()
            return int(m["total"]), int(m["active"])


# ===========================================================================
# Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_assign_program(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    fac = await _make_user(schema, "Prof One")
    admin = await _make_user(schema, "Admin One", role="ADMIN")

    out = await _assign(schema, fac, ids["mca"], admin)
    assert out.is_active is True
    assert out.faculty_user_id == fac
    assert out.program_id == ids["mca"]
    assert out.reactivated is False
    assert out.program.code == "MCA"
    assert out.faculty.full_name == "Prof One"

    total, active = await _row_count(schema, fac, ids["mca"])
    assert (total, active) == (1, 1)


@pytest.mark.asyncio
async def test_duplicate_assignment_prevented(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    fac = await _make_user(schema, "Prof Two")
    admin = await _make_user(schema, "Admin Two", role="ADMIN")

    await _assign(schema, fac, ids["mca"], admin)
    with pytest.raises(FacultyProgramServiceError) as exc:
        await _assign(schema, fac, ids["mca"], admin)
    assert exc.value.code == "DUPLICATE_ASSIGNMENT"

    # Still exactly one active row — no duplicate inserted.
    total, active = await _row_count(schema, fac, ids["mca"])
    assert (total, active) == (1, 1)


@pytest.mark.asyncio
async def test_revoke_assignment(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    fac = await _make_user(schema, "Prof Three")
    admin = await _make_user(schema, "Admin Three", role="ADMIN")

    await _assign(schema, fac, ids["mca"], admin)
    out = await _revoke(schema, fac, ids["mca"], admin)
    assert out.is_active is False
    assert out.revoked_by == admin
    assert out.revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_without_active_raises(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    fac = await _make_user(schema, "Prof None")
    admin = await _make_user(schema, "Admin None", role="ADMIN")

    with pytest.raises(FacultyProgramServiceError) as exc:
        await _revoke(schema, fac, ids["mca"], admin)
    assert exc.value.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_reactivate_assignment(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    fac = await _make_user(schema, "Prof Four")
    admin = await _make_user(schema, "Admin Four", role="ADMIN")

    first = await _assign(schema, fac, ids["mca"], admin)
    await _revoke(schema, fac, ids["mca"], admin)
    again = await _assign(schema, fac, ids["mca"], admin)

    assert again.reactivated is True
    assert again.is_active is True
    assert again.revoked_at is None
    assert again.revoked_by is None
    # Reactivation reuses the SAME row — no duplicate history.
    assert again.id == first.id
    total, active = await _row_count(schema, fac, ids["mca"])
    assert (total, active) == (1, 1)


@pytest.mark.asyncio
async def test_list_programs(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    fac = await _make_user(schema, "Prof Five")
    admin = await _make_user(schema, "Admin Five", role="ADMIN")

    await _assign(schema, fac, ids["mca"], admin)
    await _assign(schema, fac, ids["bca"], admin)

    active = await _list_programs(schema, fac)
    assert active.total == 2
    assert {i.program.code for i in active.items} == {"MCA", "BCA"}

    # Revoke one — default list drops it, include_inactive keeps it.
    await _revoke(schema, fac, ids["bca"], admin)
    active = await _list_programs(schema, fac)
    assert active.total == 1
    assert active.items[0].program.code == "MCA"

    allrows = await _list_programs(schema, fac, include_inactive=True)
    assert allrows.total == 2


@pytest.mark.asyncio
async def test_list_faculty_for_program(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    fac1 = await _make_user(schema, "Prof Six")
    fac2 = await _make_user(schema, "Prof Seven")
    admin = await _make_user(schema, "Admin Six", role="ADMIN")

    await _assign(schema, fac1, ids["mca"], admin)
    await _assign(schema, fac2, ids["mca"], admin)

    listing = await _list_faculty(schema, ids["mca"])
    assert listing.total == 2
    assert {i.faculty_user_id for i in listing.items} == {fac1, fac2}


@pytest.mark.asyncio
async def test_soft_delete_behavior(test_tenant_a):
    """Revoke never hard-deletes; the row persists with is_active=False."""
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    fac = await _make_user(schema, "Prof Eight")
    admin = await _make_user(schema, "Admin Eight", role="ADMIN")

    await _assign(schema, fac, ids["mca"], admin)
    await _revoke(schema, fac, ids["mca"], admin)

    total, active = await _row_count(schema, fac, ids["mca"])
    assert total == 1            # row still exists
    assert active == 0           # but is inactive

    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            r = await s.execute(text(
                "SELECT is_active, revoked_by, revoked_at "
                "FROM faculty_program_assignments "
                "WHERE faculty_user_id = :f AND program_id = :p"
            ), {"f": str(fac), "p": str(ids["mca"])})
            m = r.mappings().one()
    assert m["is_active"] is False
    assert m["revoked_by"] is not None
    assert m["revoked_at"] is not None


@pytest.mark.asyncio
async def test_assign_rejects_non_faculty(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    student = await _make_user(schema, "Stud One", role="STUDENT")
    admin = await _make_user(schema, "Admin Nine", role="ADMIN")

    with pytest.raises(FacultyProgramServiceError) as exc:
        await _assign(schema, student, ids["mca"], admin)
    assert exc.value.code == "INVALID_ROLE"
