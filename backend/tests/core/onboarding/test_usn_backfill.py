"""USN backfill tests — Phase 1 / Step 2.

Integration tests against a real PostgreSQL tenant schema.  They build a small
academic structure (school → dept → 2 programs → batch → semester → section),
enrol students, then exercise preview + commit:

  * projected USN ranges (reset per program)
  * existing students with USNs are skipped, never modified
  * counter seeding from existing USNs (new numbers continue past the max)
  * idempotency (second run assigns nothing)
  * error rows (no enrollment) and conflict detection
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.auth.security import hash_password
from app.core.onboarding.usn_backfill_service import UsnBackfillService

_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"statement_cache_size": 0},
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

_PW = hash_password("Student@123")


async def _setup_structure(schema: str) -> dict:
    """Create SCA school, CA dept, MCA + BCA programs (batch 2026, sem 1, section A)."""
    ids = {k: uuid.uuid4() for k in (
        "school", "dept",
        "mca", "mca_batch", "mca_sem", "mca_sec",
        "bca", "bca_batch", "bca_sem", "bca_sec",
    )}
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            await s.execute(text(
                "INSERT INTO sis_schools (id, code, name, is_active) "
                "VALUES (:id, 'SCA', 'School of Computing & Applications', true)"
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
                    "name": f"Master/Bachelor {code}", "code": code, "deg": deg})
                await s.execute(text(
                    "INSERT INTO acad_batches (id, program_id, name, start_year, end_year, is_active) "
                    "VALUES (:id, :pid, '2026-2029', 2026, 2029, true)"
                ), {"id": str(ids[f"{prog}_batch"]), "pid": str(ids[prog])})
                await s.execute(text(
                    "INSERT INTO acad_semesters (id, batch_id, number, is_active) "
                    "VALUES (:id, :bid, 1, true)"
                ), {"id": str(ids[f"{prog}_sem"]), "bid": str(ids[f"{prog}_batch"])})
                await s.execute(text(
                    "INSERT INTO acad_sections (id, semester_id, name, is_active) "
                    "VALUES (:id, :sid, 'A', true)"
                ), {"id": str(ids[f"{prog}_sec"]), "sid": str(ids[f"{prog}_sem"])})
    return ids


async def _make_student(
    schema: str,
    name: str,
    *,
    section_id: uuid.UUID | None = None,
    usn: str | None = None,
    admission_year: int | None = None,
) -> uuid.UUID:
    uid = uuid.uuid4()
    email = f"{name.lower().replace(' ', '.')}.{uid.hex[:6]}@test.edu"
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            await s.execute(text(
                "INSERT INTO users (id, email, password_hash, role, full_name, is_active) "
                "VALUES (:id, :email, :pw, 'STUDENT', :name, true)"
            ), {"id": str(uid), "email": email, "pw": _PW, "name": name})
            if section_id is not None:
                await s.execute(text(
                    "INSERT INTO acad_enrollments (id, student_id, section_id, is_active) "
                    "VALUES (:id, :sid, :sec, true)"
                ), {"id": str(uuid.uuid4()), "sid": str(uid), "sec": str(section_id)})
            if usn is not None or admission_year is not None:
                await s.execute(text(
                    "INSERT INTO sis_student_profiles (user_id, usn, admission_year) "
                    "VALUES (:uid, :usn, :yr)"
                ), {"uid": str(uid), "usn": usn, "yr": admission_year})
    return uid


async def _preview(schema: str):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await UsnBackfillService.preview(s)


async def _commit(schema: str, actor: uuid.UUID):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await UsnBackfillService.commit(s, actor_user_id=actor)


async def _usn_of(schema: str, uid: uuid.UUID) -> str | None:
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            r = await s.execute(
                text("SELECT usn FROM sis_student_profiles WHERE user_id = :u"),
                {"u": str(uid)},
            )
            return r.scalar_one_or_none()


# ===========================================================================
# Preview
# ===========================================================================

@pytest.mark.asyncio
async def test_preview_projects_ranges_reset_per_program(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    for i in range(3):
        await _make_student(schema, f"Mca Student {i}", section_id=ids["mca_sec"])
    for i in range(2):
        await _make_student(schema, f"Bca Student {i}", section_id=ids["bca_sec"])

    preview = await _preview(schema)

    assert preview.total_students == 5
    assert preview.already_have_usn == 0
    assert preview.to_assign == 5
    assert preview.errors_count == 0
    assert preview.conflicts_count == 0

    ranges = {(r.school_code, r.program_code): r for r in preview.projected_ranges}
    assert ranges[("SCA", "MCA")].first_usn == "SCA26MCA001"
    assert ranges[("SCA", "MCA")].last_usn == "SCA26MCA003"
    assert ranges[("SCA", "BCA")].first_usn == "SCA26BCA001"
    assert ranges[("SCA", "BCA")].last_usn == "SCA26BCA002"


@pytest.mark.asyncio
async def test_preview_is_read_only(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    uid = await _make_student(schema, "Solo Student", section_id=ids["mca_sec"])

    await _preview(schema)
    # No USN written, no counter row created
    assert await _usn_of(schema, uid) is None
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            cnt = (await s.execute(text("SELECT count(*) FROM usn_sequence_counters"))).scalar_one()
    assert cnt == 0


@pytest.mark.asyncio
async def test_preview_flags_unresolvable_students(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup_structure(schema)
    await _make_student(schema, "No Enrollment", section_id=None)  # cannot derive

    preview = await _preview(schema)
    assert preview.errors_count == 1
    err_row = next(r for r in preview.rows if r.action == "ERROR")
    assert "missing" in err_row.errors[0]


# ===========================================================================
# Commit
# ===========================================================================

@pytest.mark.asyncio
async def test_commit_assigns_contiguous_usns(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    admin = await _make_student(schema, "Admin Actor", section_id=None)  # actor id only
    uids = [await _make_student(schema, f"Mca {i}", section_id=ids["mca_sec"]) for i in range(3)]

    result = await _commit(schema, admin)
    assert result.assigned == 3

    usns = sorted(filter(None, [await _usn_of(schema, u) for u in uids]))
    assert usns == ["SCA26MCA001", "SCA26MCA002", "SCA26MCA003"]


@pytest.mark.asyncio
async def test_commit_skips_and_never_modifies_existing_usn(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    admin = uuid.uuid4()
    # One student already carries a (non-conventional) USN — must be untouched.
    kept = await _make_student(schema, "Has Usn", section_id=ids["mca_sec"], usn="LEGACY-999")
    fresh = await _make_student(schema, "Needs Usn", section_id=ids["mca_sec"])

    result = await _commit(schema, admin)
    assert result.skipped == 1
    assert result.assigned == 1
    assert await _usn_of(schema, kept) == "LEGACY-999"      # unchanged
    assert await _usn_of(schema, fresh) == "SCA26MCA001"


@pytest.mark.asyncio
async def test_commit_seeds_counter_from_existing_usns(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    admin = uuid.uuid4()
    # Existing conventional USN at seq 5 → new students must continue from 6.
    await _make_student(schema, "Seed Student", section_id=ids["mca_sec"],
                        usn="SCA26MCA005", admission_year=2026)
    fresh = await _make_student(schema, "After Seed", section_id=ids["mca_sec"])

    result = await _commit(schema, admin)
    assert result.counters_seeded == 1
    assert result.assigned == 1
    assert await _usn_of(schema, fresh) == "SCA26MCA006"


@pytest.mark.asyncio
async def test_commit_is_idempotent(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    admin = uuid.uuid4()
    uids = [await _make_student(schema, f"Mca {i}", section_id=ids["mca_sec"]) for i in range(3)]

    first = await _commit(schema, admin)
    assert first.assigned == 3

    first_usns = sorted(filter(None, [await _usn_of(schema, u) for u in uids]))

    second = await _commit(schema, admin)
    assert second.assigned == 0
    assert second.skipped == 3

    # USNs unchanged after the second (no-op) run
    second_usns = sorted(filter(None, [await _usn_of(schema, u) for u in uids]))
    assert first_usns == second_usns

    # Preview now reports nothing to assign
    preview = await _preview(schema)
    assert preview.to_assign == 0
    assert preview.already_have_usn == 3


@pytest.mark.asyncio
async def test_preview_detects_conflict(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup_structure(schema)
    # A student holds SCA26MCA001 but has NO enrollment, so it cannot seed the
    # MCA/2026 counter.  A fresh enrolled MCA student would project the same USN.
    await _make_student(schema, "Orphan Usn", section_id=None, usn="SCA26MCA001")
    await _make_student(schema, "Collides", section_id=ids["mca_sec"])

    preview = await _preview(schema)
    assert preview.conflicts_count == 1
    conflict_row = next(r for r in preview.rows if r.action == "CONFLICT")
    assert "already exists" in conflict_row.errors[0]
    assert conflict_row.projected_usn is None
