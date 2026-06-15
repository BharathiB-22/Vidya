"""Import-pipeline wiring tests — ERP Onboarding Phase 1 / Step 4.

Student import now mints USNs via UsnAllocator (preview projects, commit mints
into sis_student_profiles); faculty import applies program mappings via
FacultyProgramService.  Integration tests against a real PostgreSQL tenant.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.onboarding.faculty_program_service import FacultyProgramService
from app.core.onboarding.service import OnboardingService

_engine = create_async_engine(
    settings.DATABASE_URL, echo=False, connect_args={"statement_cache_size": 0},
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _setup(schema: str) -> dict:
    """SCA school → CA dept (school-linked) → MCA+BCA programs, batch 2026, sem1, sec A.
    Also an UNLINKED dept (no school) → ULP program + section, to test incomplete triple.
    """
    ids = {k: uuid.uuid4() for k in (
        "school", "dept", "mca", "bca", "batch", "sem", "sec",
        "dept_nolink", "ulp", "ulp_batch", "ulp_sem", "ulp_sec",
    )}
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
            for prog, code in (("mca", "MCA"), ("bca", "BCA")):
                await s.execute(text(
                    "INSERT INTO acad_programs "
                    "(id, department_id, name, code, degree_type, duration_years, is_active) "
                    "VALUES (:id, :dept, :name, :code, 'PG', 2, true)"
                ), {"id": str(ids[prog]), "dept": str(ids["dept"]), "name": f"Prog {code}", "code": code})
            # MCA batch/sem/section
            await s.execute(text(
                "INSERT INTO acad_batches (id, program_id, name, start_year, end_year, is_active) "
                "VALUES (:id, :pid, '2026-2028', 2026, 2028, true)"
            ), {"id": str(ids["batch"]), "pid": str(ids["mca"])})
            await s.execute(text(
                "INSERT INTO acad_semesters (id, batch_id, number, is_active) "
                "VALUES (:id, :bid, 1, true)"
            ), {"id": str(ids["sem"]), "bid": str(ids["batch"])})
            await s.execute(text(
                "INSERT INTO acad_sections (id, semester_id, name, is_active) "
                "VALUES (:id, :sid, 'A', true)"
            ), {"id": str(ids["sec"]), "sid": str(ids["sem"])})
            # Unlinked dept (no school) → program + chain
            await s.execute(text(
                "INSERT INTO acad_departments (id, school_id, name, code, is_active) "
                "VALUES (:id, NULL, 'Unlinked', 'UL', true)"
            ), {"id": str(ids["dept_nolink"])})
            await s.execute(text(
                "INSERT INTO acad_programs "
                "(id, department_id, name, code, degree_type, duration_years, is_active) "
                "VALUES (:id, :dept, 'Unlinked Prog', 'ULP', 'PG', 2, true)"
            ), {"id": str(ids["ulp"]), "dept": str(ids["dept_nolink"])})
            await s.execute(text(
                "INSERT INTO acad_batches (id, program_id, name, start_year, end_year, is_active) "
                "VALUES (:id, :pid, '2026-2028', 2026, 2028, true)"
            ), {"id": str(ids["ulp_batch"]), "pid": str(ids["ulp"])})
            await s.execute(text(
                "INSERT INTO acad_semesters (id, batch_id, number, is_active) "
                "VALUES (:id, :bid, 1, true)"
            ), {"id": str(ids["ulp_sem"]), "bid": str(ids["ulp_batch"])})
            await s.execute(text(
                "INSERT INTO acad_sections (id, semester_id, name, is_active) "
                "VALUES (:id, :sid, 'A', true)"
            ), {"id": str(ids["ulp_sec"]), "sid": str(ids["ulp_sem"])})
    return ids


async def _admin(schema: str) -> uuid.UUID:
    uid = uuid.uuid4()
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            await s.execute(text(
                "INSERT INTO users (id, email, password_hash, role, full_name, is_active) "
                "VALUES (:id, :e, 'x', 'ADMIN', 'Admin', true)"
            ), {"id": str(uid), "e": f"admin.{uid.hex[:6]}@t.edu"})
    return uid


def _students_csv(names_emails: list[tuple[str, str]]) -> bytes:
    body = "full_name,email\n" + "".join(f"{n},{e}\n" for n, e in names_emails)
    return body.encode()


async def _preview_students(schema, content, program_id, section_id):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await OnboardingService.preview_students_csv(
                content, s, context_program_id=program_id, context_section_id=section_id,
            )


async def _commit_students(schema, content, program_id, section_id):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await OnboardingService.commit_students_csv(
                content, "Student@123", s,
                context_program_id=program_id, context_section_id=section_id,
            )


async def _usn_of(schema, email) -> str | None:
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            r = await s.execute(text(
                "SELECT sp.usn FROM sis_student_profiles sp "
                "JOIN users u ON u.id = sp.user_id WHERE LOWER(u.email) = :e"
            ), {"e": email.lower()})
            return r.scalar_one_or_none()


# ===========================================================================
# Student import — USN minting
# ===========================================================================

@pytest.mark.asyncio
async def test_preview_projects_usns(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema)
    content = _students_csv([("Anu A", "anu@t.edu"), ("Bala B", "bala@t.edu")])

    preview = await _preview_students(schema, content, ids["mca"], ids["sec"])

    assert preview.valid_rows == 2
    projected = sorted(r.projected_usn for r in preview.rows if r.projected_usn)
    assert projected == ["SCA26MCA001", "SCA26MCA002"]
    assert len(preview.projected_usn_ranges) == 1
    rng = preview.projected_usn_ranges[0]
    assert (rng.school_code, rng.program_code, rng.admission_year) == ("SCA", "MCA", 2026)
    assert (rng.first_usn, rng.last_usn) == ("SCA26MCA001", "SCA26MCA002")


@pytest.mark.asyncio
async def test_preview_is_read_only(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema)
    content = _students_csv([("Anu A", "anu@t.edu")])
    await _preview_students(schema, content, ids["mca"], ids["sec"])
    # No USN written, no counter row created.
    assert await _usn_of(schema, "anu@t.edu") is None
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            cnt = (await s.execute(text("SELECT count(*) FROM usn_sequence_counters"))).scalar_one()
    assert cnt == 0


@pytest.mark.asyncio
async def test_commit_mints_usns(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema)
    content = _students_csv([("Anu A", "anu@t.edu"), ("Bala B", "bala@t.edu"),
                             ("Chap C", "chap@t.edu")])

    result = await _commit_students(schema, content, ids["mca"], ids["sec"])
    assert result.created == 3
    assert result.usns_assigned == 3
    assert result.enrollments_created == 3

    usns = sorted(filter(None, [await _usn_of(schema, e)
                                for e in ("anu@t.edu", "bala@t.edu", "chap@t.edu")]))
    assert usns == ["SCA26MCA001", "SCA26MCA002", "SCA26MCA003"]


@pytest.mark.asyncio
async def test_commit_uses_allocator_not_identifier(test_tenant_a):
    """USN comes from UsnAllocator into sis_student_profiles, not the CSV identifier."""
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema)
    # Even with an 'identifier' column the canonical USN is system-minted.
    content = b"full_name,email,identifier\nAnu A,anu@t.edu,MANUAL999\n"
    result = await _commit_students(schema, content, ids["mca"], ids["sec"])
    assert result.usns_assigned == 1
    assert await _usn_of(schema, "anu@t.edu") == "SCA26MCA001"


@pytest.mark.asyncio
async def test_second_batch_continues_sequence(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema)
    await _commit_students(schema, _students_csv(
        [("A", "a@t.edu"), ("B", "b@t.edu"), ("C", "c@t.edu")]), ids["mca"], ids["sec"])
    r2 = await _commit_students(schema, _students_csv(
        [("D", "d@t.edu"), ("E", "e@t.edu")]), ids["mca"], ids["sec"])
    assert r2.usns_assigned == 2
    assert sorted(filter(None, [await _usn_of(schema, e) for e in ("d@t.edu", "e@t.edu")])) \
        == ["SCA26MCA004", "SCA26MCA005"]


@pytest.mark.asyncio
async def test_reimport_is_idempotent(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema)
    content = _students_csv([("A", "a@t.edu"), ("B", "b@t.edu")])
    first = await _commit_students(schema, content, ids["mca"], ids["sec"])
    assert first.usns_assigned == 2

    second = await _commit_students(schema, content, ids["mca"], ids["sec"])
    assert second.created == 0          # emails already exist
    assert second.usns_assigned == 0
    # USNs unchanged
    assert await _usn_of(schema, "a@t.edu") in ("SCA26MCA001", "SCA26MCA002")


@pytest.mark.asyncio
async def test_incomplete_triple_warns_no_usn(test_tenant_a):
    """Program with no school link → student created, but no USN minted."""
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema)
    content = _students_csv([("No School", "ns@t.edu")])
    result = await _commit_students(schema, content, ids["ulp"], ids["ulp_sec"])
    assert result.created == 1
    assert result.usns_assigned == 0
    assert await _usn_of(schema, "ns@t.edu") is None
    # Preview surfaces the warning.
    preview = await _preview_students(schema, content, ids["ulp"], ids["ulp_sec"])
    assert any(w for r in preview.rows for w in r.warnings)


# ===========================================================================
# Faculty import — program mappings
# ===========================================================================

async def _commit_faculty(schema, content, actor):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await OnboardingService.commit_faculty_csv(
                content, "Faculty@123", s, actor_user_id=actor,
            )


async def _active_programs_for(schema, email) -> list[str]:
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            r = await s.execute(text(
                "SELECT p.code FROM faculty_program_assignments fpa "
                "JOIN users u ON u.id = fpa.faculty_user_id "
                "JOIN acad_programs p ON p.id = fpa.program_id "
                "WHERE LOWER(u.email) = :e AND fpa.is_active = true ORDER BY p.code"
            ), {"e": email.lower()})
            return [row[0] for row in r.fetchall()]


@pytest.mark.asyncio
async def test_faculty_import_creates_mappings(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    admin = await _admin(schema)
    content = b"full_name,email,program_codes\nDr X,x@t.edu,MCA|BCA\n"
    result = await _commit_faculty(schema, content, admin)
    assert result.created == 1
    assert result.program_mappings_created == 2
    assert await _active_programs_for(schema, "x@t.edu") == ["BCA", "MCA"]


@pytest.mark.asyncio
async def test_faculty_duplicate_mapping_skipped(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    admin = await _admin(schema)
    content = b"full_name,email,program_codes\nDr X,x@t.edu,MCA\n"
    await _commit_faculty(schema, content, admin)
    # Re-import same faculty+program: user-create skipped, mapping already active.
    again = await _commit_faculty(schema, content, admin)
    assert again.created == 0
    assert again.program_mappings_skipped == 1
    assert again.program_mappings_created == 0


@pytest.mark.asyncio
async def test_faculty_mapping_reactivated(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema)
    admin = await _admin(schema)
    content = b"full_name,email,program_codes\nDr X,x@t.edu,MCA|BCA\n"
    await _commit_faculty(schema, content, admin)

    # Revoke MCA, then re-import: MCA reactivated, BCA still active (skipped).
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            fac = (await s.execute(text("SELECT id FROM users WHERE email = 'x@t.edu'"))).scalar_one()
            await FacultyProgramService.revoke_program(
                s, faculty_user_id=fac, program_id=ids["mca"], revoked_by=admin,
            )

    again = await _commit_faculty(schema, content, admin)
    assert again.program_mappings_reactivated == 1
    assert again.program_mappings_skipped == 1
    assert await _active_programs_for(schema, "x@t.edu") == ["BCA", "MCA"]


@pytest.mark.asyncio
async def test_faculty_unknown_program_code_warns(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    admin = await _admin(schema)
    content = b"full_name,email,program_codes\nDr Y,y@t.edu,MCA|ZZZ\n"
    result = await _commit_faculty(schema, content, admin)
    assert result.created == 1                       # user still created
    assert result.program_mappings_created == 1      # only MCA mapped
    assert await _active_programs_for(schema, "y@t.edu") == ["MCA"]
