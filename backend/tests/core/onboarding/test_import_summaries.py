"""Import preview summaries (summary_meta) — ERP Onboarding Phase 1 / Step 6.

Dashboard-ready rollups on the student & faculty import previews.  Integration
tests against a real PostgreSQL tenant schema.
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
    """SCA school → CA dept → MCA + BCA programs, each with batch 2026 / sem1 / sec A."""
    ids = {k: uuid.uuid4() for k in (
        "school", "dept", "mca", "bca",
        "mca_batch", "mca_sem", "mca_sec", "bca_batch", "bca_sem", "bca_sec",
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
                await s.execute(text(
                    "INSERT INTO acad_batches (id, program_id, name, start_year, end_year, is_active) "
                    "VALUES (:id, :pid, '2026-2028', 2026, 2028, true)"
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


async def _preview_students(schema, content):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await OnboardingService.preview_students_csv(content, s)


async def _preview_faculty(schema, content):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await OnboardingService.preview_faculty_csv(content, s)


async def _commit_faculty(schema, content, actor):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await OnboardingService.commit_faculty_csv(content, "Faculty@123", s, actor_user_id=actor)


# ===========================================================================
# Student summary_meta
# ===========================================================================

@pytest.mark.asyncio
async def test_student_summary_meta(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    # 2 MCA + 1 BCA valid; 1 unknown program (invalid).
    content = (
        "full_name,email,program_code,batch_year,section_name\n"
        "A,a@t.edu,MCA,2026,A\n"
        "B,b@t.edu,MCA,2026,A\n"
        "C,c@t.edu,BCA,2026,A\n"
        "D,d@t.edu,ZZZ,2026,A\n"
    ).encode()

    preview = await _preview_students(schema, content)
    sm = preview.summary_meta
    assert sm is not None
    assert (sm["total_rows"], sm["valid_rows"], sm["invalid_rows"]) == (4, 3, 1)
    assert sm["schools_count"] == 1
    assert sm["departments_count"] == 1
    assert sm["programs_count"] == 2          # MCA + BCA
    assert sm["batches_count"] == 2           # (MCA,2026), (BCA,2026)
    assert sm["sections_count"] == 2
    assert sm["projected_usns_count"] == 3
    assert sm["new_programs"] == 1            # ZZZ
    assert sm["new_schools"] == 0
    assert sm["new_departments"] == 0


@pytest.mark.asyncio
async def test_student_new_batch_and_section_counts(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    content = (
        "full_name,email,program_code,batch_year,section_name\n"
        "A,a@t.edu,MCA,2099,A\n"   # batch year not present → new_batch
        "B,b@t.edu,MCA,2026,Z\n"   # batch exists, section Z missing → new_section
    ).encode()
    preview = await _preview_students(schema, content)
    sm = preview.summary_meta
    assert sm["valid_rows"] == 0
    assert sm["new_batches"] == 1
    assert sm["new_sections"] == 1


@pytest.mark.asyncio
async def test_student_projected_ranges(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    content = (
        "full_name,email,program_code,batch_year,section_name\n"
        "A,a@t.edu,MCA,2026,A\n"
        "B,b@t.edu,MCA,2026,A\n"
        "C,c@t.edu,BCA,2026,A\n"
    ).encode()
    preview = await _preview_students(schema, content)
    ranges = {r.program_code: r for r in preview.projected_usn_ranges}
    assert set(ranges) == {"MCA", "BCA"}
    assert (ranges["MCA"].first_usn, ranges["MCA"].last_usn) == ("SCA26MCA001", "SCA26MCA002")
    assert (ranges["BCA"].first_usn, ranges["BCA"].last_usn) == ("SCA26BCA001", "SCA26BCA001")


# ===========================================================================
# Faculty summary_meta + program_assignment_summary
# ===========================================================================

@pytest.mark.asyncio
async def test_faculty_summary_meta_new(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    content = (
        "full_name,email,program_codes\n"
        "Dr A,fa@t.edu,MCA|BCA\n"
        "Dr B,fb@t.edu,MCA\n"
    ).encode()
    preview = await _preview_faculty(schema, content)
    sm = preview.summary_meta
    assert (sm["total_rows"], sm["valid_rows"], sm["invalid_rows"]) == (2, 2, 0)
    assert sm["faculty_count"] == 2
    assert sm["unique_programs"] == 2
    assert sm["new_program_assignments"] == 3     # A→MCA,BCA ; B→MCA
    assert sm["reactivated_assignments"] == 0


@pytest.mark.asyncio
async def test_faculty_program_assignment_summary(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    content = (
        "full_name,email,program_codes\n"
        "Dr A,fa@t.edu,MCA|BCA\n"
        "Dr B,fb@t.edu,MCA\n"
        "Dr C,fc@t.edu,MCA\n"
    ).encode()
    preview = await _preview_faculty(schema, content)
    pas = {p.program_code: p.faculty_count for p in preview.program_assignment_summary}
    assert pas == {"MCA": 3, "BCA": 1}


@pytest.mark.asyncio
async def test_faculty_summary_predicts_reactivation(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema)
    admin = await _admin(schema)
    content = b"full_name,email,program_codes\nDr A,fa@t.edu,MCA|BCA\n"
    # First import creates the faculty + both mappings.
    await _commit_faculty(schema, content, admin)
    # Revoke MCA so a re-import would reactivate it.
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            fac = (await s.execute(text("SELECT id FROM users WHERE email='fa@t.edu'"))).scalar_one()
            await FacultyProgramService.revoke_program(
                s, faculty_user_id=fac, program_id=ids["mca"], revoked_by=admin,
            )

    preview = await _preview_faculty(schema, content)
    sm = preview.summary_meta
    # Faculty already exists (row invalid for creation) but mappings are predicted:
    assert sm["reactivated_assignments"] == 1     # MCA
    assert sm["new_program_assignments"] == 0     # BCA still active → neither new nor reactivated
    assert sm["faculty_count"] == 1               # existing faculty still counted (has mappings)
