"""Institution email auto-generation on student import — Phase 1.3.

Verifies that commit_students_csv generates institution emails for newly
created students that received a USN, when an institution_domain is configured.
Also verifies graceful skip when no domain is set.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.onboarding.service import OnboardingService

_engine = create_async_engine(
    settings.DATABASE_URL, echo=False, connect_args={"statement_cache_size": 0},
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

# SCHEMA_A is set up by test_tenant_a fixture
SCHEMA_A = "tenant_test_a"


async def _set_domain(schema: str, domain: str | None) -> None:
    async with _Session() as s:
        async with s.begin():
            await s.execute(
                text("UPDATE public.tenants SET institution_domain = :d WHERE schema_name = :s"),
                {"d": domain, "s": schema},
            )


async def _setup(schema: str) -> dict:
    """SCA school → CA dept → MCA program, batch 2026, sem1, sec A."""
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
                "VALUES (:id, :dept, 'MCA', 'MCA', 'PG', 2, true)"
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


async def _commit_students_with_domain(schema: str, content: bytes, ids: dict) -> object:
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await OnboardingService.commit_students_csv(
                content, "Student@123", s,
                context_program_id=ids["mca"],
                context_section_id=ids["sec"],
                schema_name=schema,
            )


async def _inst_email_of(schema: str, email: str) -> str | None:
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            r = await s.execute(
                text("SELECT institution_email FROM users WHERE LOWER(email) = :e"),
                {"e": email.lower()},
            )
            return r.scalar_one_or_none()


async def _personal_email_of(schema: str, email: str) -> str | None:
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            r = await s.execute(
                text("SELECT personal_email FROM users WHERE LOWER(email) = :e"),
                {"e": email.lower()},
            )
            return r.scalar_one_or_none()


def _csv(*rows: tuple[str, str]) -> bytes:
    return ("full_name,email\n" + "".join(f"{n},{e}\n" for n, e in rows)).encode()


# ===========================================================================
# 1. Domain configured → institution emails generated on import
# ===========================================================================

@pytest.mark.asyncio
async def test_import_generates_institution_email_when_domain_set(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _set_domain(schema, "test.edu")
    ids = await _setup(schema)
    content = _csv(("Anu A", "anu@gmail.com"), ("Bala B", "bala@gmail.com"))

    result = await _commit_students_with_domain(schema, content, ids)

    assert result.created == 2
    assert result.usns_assigned == 2
    assert result.institution_emails_assigned == 2

    inst1 = await _inst_email_of(schema, "anu@gmail.com")
    inst2 = await _inst_email_of(schema, "bala@gmail.com")
    # USNs are SCA26MCA001 and SCA26MCA002 → emails are lowercased
    assert inst1 == "sca26mca001@test.edu"
    assert inst2 == "sca26mca002@test.edu"


@pytest.mark.asyncio
async def test_personal_email_backfilled_from_login_email(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _set_domain(schema, "uni.edu")
    ids = await _setup(schema)
    content = _csv(("Chandra C", "chandra@personal.com"))

    await _commit_students_with_domain(schema, content, ids)

    personal = await _personal_email_of(schema, "chandra@personal.com")
    assert personal == "chandra@personal.com"


# ===========================================================================
# 2. No domain configured → graceful skip (no crash, no emails)
# ===========================================================================

@pytest.mark.asyncio
async def test_import_skips_institution_email_when_no_domain(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _set_domain(schema, None)  # clear domain
    ids = await _setup(schema)
    content = _csv(("Dev D", "dev@t.edu"))

    result = await _commit_students_with_domain(schema, content, ids)

    assert result.created == 1
    assert result.usns_assigned == 1
    assert result.institution_emails_assigned == 0
    assert await _inst_email_of(schema, "dev@t.edu") is None


# ===========================================================================
# 3. Idempotent — second import does not overwrite existing institution email
# ===========================================================================

@pytest.mark.asyncio
async def test_institution_email_not_overwritten_on_reimport(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _set_domain(schema, "first.edu")
    ids = await _setup(schema)
    content = _csv(("Eva E", "eva@g.com"))

    # First import assigns institution email
    r1 = await _commit_students_with_domain(schema, content, ids)
    assert r1.institution_emails_assigned == 1
    email_after_first = await _inst_email_of(schema, "eva@g.com")
    assert email_after_first == "sca26mca001@first.edu"

    # Domain changes — but eva's email should NOT be overwritten
    await _set_domain(schema, "second.edu")
    # Re-importing same email is a DB-dup → skipped, so no change
    r2 = await _commit_students_with_domain(schema, content, ids)
    assert r2.created == 0  # duplicate, skipped
    assert r2.institution_emails_assigned == 0
    # Email unchanged
    assert await _inst_email_of(schema, "eva@g.com") == email_after_first


# ===========================================================================
# 4. schema_name=None → graceful skip (no crash)
# ===========================================================================

@pytest.mark.asyncio
async def test_import_without_schema_name_gracefully_skips(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _set_domain(schema, "x.edu")
    ids = await _setup(schema)
    content = _csv(("Fiona F", "fiona@t.edu"))

    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            result = await OnboardingService.commit_students_csv(
                content, "Student@123", s,
                context_program_id=ids["mca"],
                context_section_id=ids["sec"],
                schema_name=None,  # no schema_name supplied
            )

    assert result.created == 1
    assert result.institution_emails_assigned == 0
