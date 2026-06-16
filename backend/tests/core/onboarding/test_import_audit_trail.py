"""Onboarding import audit trail — ERP Onboarding Phase 1.1 (Task A).

The onboarding commit flow must record a SisImportBatch and stamp import_batch_id
onto the student profiles it creates, so SIS → Import History (GET /sis/imports →
ImportBatchService.list_batches) shows onboarding imports — mirroring the older
bulk-import flow.  Integration tests against a real PostgreSQL tenant schema.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.onboarding.service import OnboardingService
from app.modules.m11_sis.import_batch_service import ImportBatchService

_engine = create_async_engine(
    settings.DATABASE_URL, echo=False, connect_args={"statement_cache_size": 0},
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _setup(schema: str) -> dict:
    """SCA school → CA dept → MCA program → batch 2026 / sem1 / section A."""
    ids = {k: uuid.uuid4() for k in ("school", "dept", "mca", "batch", "sem", "sec")}
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
            await s.execute(text(
                "INSERT INTO acad_programs "
                "(id, department_id, name, code, degree_type, duration_years, is_active) "
                "VALUES (:id, :dept, 'Prog MCA', 'MCA', 'PG', 2, true)"
            ), {"id": str(ids["mca"]), "dept": str(ids["dept"])})
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


async def _commit_students(schema, content, actor, filename="students_batch1.csv"):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await OnboardingService.commit_students_csv(
                content, "Student@123", s, actor_user_id=actor, filename=filename,
            )


async def _list_batches(schema):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await ImportBatchService.list_batches(s)


def _students_csv() -> bytes:
    return (
        "full_name,email,program_code,batch_year,section_name\n"
        "Alice Roy,alice@t.edu,MCA,2026,A\n"
        "Bob Sen,bob@t.edu,MCA,2026,A\n"
    ).encode()


# ===========================================================================
# Task A — student import audit trail
# ===========================================================================

@pytest.mark.asyncio
async def test_onboarding_student_import_creates_batch(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    admin = await _admin(schema)

    result = await _commit_students(schema, _students_csv(), admin)
    assert result.created == 2

    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            row = (await s.execute(text(
                "SELECT batch_ref, imported_by, record_type, source_filename, "
                "       total_records, success_count, failed_count, is_rolled_back "
                "FROM sis_import_batches"
            ))).mappings().all()

    assert len(row) == 1
    b = row[0]
    assert b["record_type"] == "STUDENT"
    assert b["imported_by"] == admin
    assert b["source_filename"] == "students_batch1.csv"
    assert (b["total_records"], b["success_count"], b["failed_count"]) == (2, 2, 0)
    assert b["is_rolled_back"] is False
    assert b["batch_ref"].startswith("IMPORT-")


@pytest.mark.asyncio
async def test_onboarding_student_import_stamps_batch_id(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    admin = await _admin(schema)

    await _commit_students(schema, _students_csv(), admin)

    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            batch_id = (await s.execute(text("SELECT id FROM sis_import_batches"))).scalar_one()
            profiles = (await s.execute(text(
                "SELECT user_id, usn, import_batch_id FROM sis_student_profiles"
            ))).mappings().all()

    assert len(profiles) == 2
    # Every created profile is stamped with the batch that produced it.
    assert all(p["import_batch_id"] == batch_id for p in profiles)
    assert all(p["usn"] for p in profiles)  # USNs were minted in the same run


@pytest.mark.asyncio
async def test_import_history_endpoint_returns_onboarding_batch(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    admin = await _admin(schema)

    await _commit_students(schema, _students_csv(), admin)

    # ImportBatchService.list_batches is exactly what GET /sis/imports calls.
    rows, total = await _list_batches(schema)
    assert total == 1
    assert len(rows) == 1
    assert rows[0].record_type == "STUDENT"
    assert rows[0].source_filename == "students_batch1.csv"
    assert rows[0].success_count == 2


@pytest.mark.asyncio
async def test_two_onboarding_imports_produce_two_batches(test_tenant_a):
    """Distinct commits are distinct audit batches (no overwrite/merge)."""
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    admin = await _admin(schema)

    await _commit_students(schema, _students_csv(), admin, filename="first.csv")
    second = (
        "full_name,email,program_code,batch_year,section_name\n"
        "Carol Das,carol@t.edu,MCA,2026,A\n"
    ).encode()
    await _commit_students(schema, second, admin, filename="second.csv")

    rows, total = await _list_batches(schema)
    assert total == 2
    files = {r.source_filename for r in rows}
    assert files == {"first.csv", "second.csv"}


@pytest.mark.asyncio
async def test_onboarding_faculty_import_creates_batch(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    admin = await _admin(schema)

    content = b"full_name,email,program_codes\nDr A,fa@t.edu,MCA\nDr B,fb@t.edu,MCA\n"
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            res = await OnboardingService.commit_faculty_csv(
                content, "Faculty@123", s,
                filename="faculty1.csv", actor_user_id=admin,
            )
    assert res.created == 2

    rows, total = await _list_batches(schema)
    assert total == 1
    assert rows[0].record_type == "FACULTY"
    assert rows[0].source_filename == "faculty1.csv"
