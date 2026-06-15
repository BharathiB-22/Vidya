"""USN code immutability governance — ERP Onboarding Phase 1 / Step 5.

Once a USN ({SchoolCode}{YY}{ProgramCode}{Seq}) is issued, its school code and
program code are frozen; names remain editable.  Integration tests against a
real PostgreSQL tenant schema.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.onboarding.usn_governance import (
    ProgramCodeUsageService,
    SchoolCodeUsageService,
)
from app.modules.m11_sis.schemas import SchoolUpdate
from app.modules.m11_sis.service import SchoolService, SchoolServiceError
from app.modules.m_academics.schemas import ProgramUpdate
from app.modules.m_academics.service import AcadServiceError, ProgramService

_engine = create_async_engine(
    settings.DATABASE_URL, echo=False, connect_args={"statement_cache_size": 0},
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _setup(schema: str, *, issue_usn: bool) -> dict:
    """SCA school → CA dept → MCA program; optionally one issued USN SCA26MCA001.

    Also a second, totally unused SCB school + MCB program (no USNs).
    """
    ids = {k: uuid.uuid4() for k in ("school", "dept", "mca", "school2", "dept2", "mcb", "stu")}
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            await s.execute(text(
                "INSERT INTO sis_schools (id, code, name, is_active) "
                "VALUES (:id, 'SCA', 'School of Computing', true)"
            ), {"id": str(ids["school"])})
            await s.execute(text(
                "INSERT INTO sis_schools (id, code, name, is_active) "
                "VALUES (:id, 'SCB', 'School of Business', true)"
            ), {"id": str(ids["school2"])})
            await s.execute(text(
                "INSERT INTO acad_departments (id, school_id, name, code, is_active) "
                "VALUES (:id, :sch, 'Computer Applications', 'CA', true)"
            ), {"id": str(ids["dept"]), "sch": str(ids["school"])})
            await s.execute(text(
                "INSERT INTO acad_departments (id, school_id, name, code, is_active) "
                "VALUES (:id, :sch, 'Business', 'BU', true)"
            ), {"id": str(ids["dept2"]), "sch": str(ids["school2"])})
            await s.execute(text(
                "INSERT INTO acad_programs "
                "(id, department_id, name, code, degree_type, duration_years, is_active) "
                "VALUES (:id, :dept, 'Master of CA', 'MCA', 'PG', 2, true)"
            ), {"id": str(ids["mca"]), "dept": str(ids["dept"])})
            await s.execute(text(
                "INSERT INTO acad_programs "
                "(id, department_id, name, code, degree_type, duration_years, is_active) "
                "VALUES (:id, :dept, 'Master of CB', 'MCB', 'PG', 2, true)"
            ), {"id": str(ids["mcb"]), "dept": str(ids["dept2"])})
            if issue_usn:
                await s.execute(text(
                    "INSERT INTO users (id, email, password_hash, role, full_name, is_active) "
                    "VALUES (:id, :e, 'x', 'STUDENT', 'Stu', true)"
                ), {"id": str(ids["stu"]), "e": f"stu.{ids['stu'].hex[:6]}@t.edu"})
                await s.execute(text(
                    "INSERT INTO sis_student_profiles (user_id, usn, admission_year) "
                    "VALUES (:uid, 'SCA26MCA001', 2026)"
                ), {"uid": str(ids["stu"])})
    return ids


async def _update_school(schema, school_id, **fields):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await SchoolService.update_school(
                school_id, SchoolUpdate(**fields),
                actor_user_id=uuid.uuid4(), actor_role="ADMIN",
                tenant_id=uuid.uuid4(), schema_name=schema, db=s,
            )


async def _update_program(schema, prog_id, **fields):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await ProgramService.update(prog_id, ProgramUpdate(**fields), db=s)


# ===========================================================================
# School code immutability
# ===========================================================================

@pytest.mark.asyncio
async def test_school_code_change_blocked_after_usn(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema, issue_usn=True)
    with pytest.raises(SchoolServiceError) as exc:
        await _update_school(schema, ids["school"], code="SCI")
    assert exc.value.code == "USN_CODE_LOCKED"
    assert exc.value.status_code == 409
    assert exc.value.message == "School code cannot be changed because issued USNs depend on it."


@pytest.mark.asyncio
async def test_school_name_change_allowed_after_usn(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema, issue_usn=True)
    school = await _update_school(schema, ids["school"], name="Renamed Computing School")
    assert school.name == "Renamed Computing School"
    assert school.code == "SCA"


@pytest.mark.asyncio
async def test_unused_school_code_change_allowed(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema, issue_usn=True)
    # SCB has no issued USNs → code change permitted.
    school = await _update_school(schema, ids["school2"], code="SCX")
    assert school.code == "SCX"


# ===========================================================================
# Program code immutability
# ===========================================================================

@pytest.mark.asyncio
async def test_program_code_change_blocked_after_usn(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema, issue_usn=True)
    with pytest.raises(AcadServiceError) as exc:
        await _update_program(schema, ids["mca"], code="MCS")
    assert exc.value.code == "USN_CODE_LOCKED"
    assert exc.value.status_code == 409
    assert exc.value.message == "Program code cannot be changed because issued USNs depend on it."


@pytest.mark.asyncio
async def test_program_name_change_allowed_after_usn(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema, issue_usn=True)
    prog = await _update_program(schema, ids["mca"], name="Master of Computer Apps")
    assert prog.name == "Master of Computer Apps"
    assert prog.code == "MCA"


@pytest.mark.asyncio
async def test_unused_program_code_change_allowed(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema, issue_usn=True)
    # MCB has no issued USNs → code change permitted.
    prog = await _update_program(schema, ids["mcb"], code="MCC")
    assert prog.code == "MCC"


@pytest.mark.asyncio
async def test_code_change_allowed_before_any_usn(test_tenant_a):
    """With zero issued USNs, both school and program codes are still editable."""
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema, issue_usn=False)
    school = await _update_school(schema, ids["school"], code="SCI")
    assert school.code == "SCI"
    prog = await _update_program(schema, ids["mca"], code="MCS")
    assert prog.code == "MCS"


# ===========================================================================
# Helper precision (no false positives)
# ===========================================================================

@pytest.mark.asyncio
async def test_usage_helpers_are_structural(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema, issue_usn=True)   # only SCA26MCA001 issued
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            # Exact codes are detected.
            assert await SchoolCodeUsageService.is_school_code_used("SCA", s) is True
            assert await ProgramCodeUsageService.is_program_code_used("MCA", s) is True
            # Prefixes / substrings must NOT false-match.
            assert await SchoolCodeUsageService.is_school_code_used("SC", s) is False
            assert await ProgramCodeUsageService.is_program_code_used("CA", s) is False
            assert await ProgramCodeUsageService.is_program_code_used("MC", s) is False
            # Unrelated codes.
            assert await SchoolCodeUsageService.is_school_code_used("SCB", s) is False
            assert await ProgramCodeUsageService.is_program_code_used("MCB", s) is False
