"""Faculty onboarding v2 — CSV import + identity backfill (ERP Phase 1.5).

Covers: personal_email login mapping, auto faculty_code, auto institution_email,
program assignments, responsibility grants, legacy header back-compat, unknown
role warnings, and the identity backfill for existing faculty (admins untouched).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.onboarding.faculty_backfill_service import FacultyBackfillService
from app.core.onboarding.service import OnboardingService

_engine = create_async_engine(
    settings.DATABASE_URL, echo=False, connect_args={"statement_cache_size": 0},
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _setup(schema: str, domain: str = "lms.edu") -> dict:
    ids = {k: uuid.uuid4() for k in ("school", "dept", "mca", "bca")}
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            await s.execute(
                text("UPDATE public.tenants SET institution_domain = :d WHERE schema_name = :s"),
                {"d": domain, "s": schema},
            )
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


async def _preview(schema, content):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await OnboardingService.preview_faculty_csv(content, s)


async def _commit(schema, content, actor):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            return await OnboardingService.commit_faculty_csv(
                content, "Faculty@123", s, actor_user_id=actor, actor_role="ADMIN",
            )


async def _profile(schema, email):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            r = await s.execute(text(
                "SELECT u.email, u.personal_email, u.role, p.faculty_code, p.institution_email "
                "FROM users u LEFT JOIN sis_faculty_profiles p ON p.user_id = u.id "
                "WHERE LOWER(u.email) = :e"
            ), {"e": email.lower()})
            return r.mappings().one_or_none()


async def _grants(schema, email):
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            r = await s.execute(text(
                "SELECT g.role_code FROM faculty_role_grants g "
                "JOIN users u ON u.id = g.faculty_user_id "
                "WHERE LOWER(u.email) = :e AND g.is_active = true"
            ), {"e": email.lower()})
            return {row[0] for row in r.fetchall()}


_CSV = (
    "full_name,personal_email,program_codes,roles\n"
    "Dr Kavya,kavya@gmail.com,BCA|MCA,GUIDE|EVALUATOR\n"
    "Dr Arun,arun@yahoo.com,MCA,DEAN\n"
    "Dr Meena,meena@gmail.com,BCA|MCA,BOARD\n"
).encode()


# ===========================================================================
# Preview
# ===========================================================================

@pytest.mark.asyncio
async def test_preview_projects_identity_and_roles(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    preview = await _preview(schema, _CSV)

    assert preview.valid_rows == 3
    kavya = next(r for r in preview.rows if r.full_name == "Dr Kavya")
    assert kavya.projected_faculty_code == "FAC0001"
    assert kavya.projected_institution_email == "kavya@lms.edu"
    assert set(kavya.resolved_roles) == {"GUIDE", "EVALUATOR"}
    sm = preview.summary_meta
    assert sm["faculty_codes_to_assign"] == 3
    assert sm["new_role_grants"] == 4   # GUIDE+EVALUATOR + DEAN + BOARD


@pytest.mark.asyncio
async def test_preview_unknown_role_warns(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    content = "full_name,personal_email,roles\nDr Z,z@gmail.com,HOD|GUIDE\n".encode()
    preview = await _preview(schema, content)
    row = preview.rows[0]
    assert row.resolved_roles == ["GUIDE"]
    assert row.unresolved_roles == ["HOD"]
    assert any("HOD" in w for w in row.warnings)


# ===========================================================================
# Commit
# ===========================================================================

@pytest.mark.asyncio
async def test_commit_creates_identity_programs_grants(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    admin = await _admin(schema)
    result = await _commit(schema, _CSV, admin)

    assert result.created == 3
    assert result.faculty_codes_assigned == 3
    assert result.faculty_institution_emails_assigned == 3
    assert result.program_mappings_created == 5   # Kavya BCA+MCA, Arun MCA, Meena BCA+MCA
    assert result.role_grants_created == 4

    kavya = await _profile(schema, "kavya@gmail.com")
    assert kavya["role"] == "FACULTY"
    assert kavya["email"] == "kavya@gmail.com"          # login identity = personal email
    assert kavya["personal_email"] == "kavya@gmail.com"
    assert kavya["faculty_code"] == "FAC0001"
    assert kavya["institution_email"] == "kavya@lms.edu"
    assert await _grants(schema, "kavya@gmail.com") == {"GUIDE", "EVALUATOR"}
    assert await _grants(schema, "arun@yahoo.com") == {"DEAN"}
    assert await _grants(schema, "meena@gmail.com") == {"BOARD"}


@pytest.mark.asyncio
async def test_legacy_email_header_still_works(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    admin = await _admin(schema)
    content = "full_name,email,program_codes\nDr Old,old@gmail.com,MCA\n".encode()
    result = await _commit(schema, content, admin)
    assert result.created == 1
    prof = await _profile(schema, "old@gmail.com")
    assert prof["faculty_code"] == "FAC0001"
    assert prof["personal_email"] == "old@gmail.com"


@pytest.mark.asyncio
async def test_distinct_handles_collision_suffix(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    admin = await _admin(schema)
    content = (
        "full_name,personal_email\n"
        "Dr Kavya,kavya@gmail.com\n"
        "Dr Kavya Rao,kavya.rao@gmail.com\n"
    ).encode()
    result = await _commit(schema, content, admin)
    assert result.created == 2
    a = await _profile(schema, "kavya@gmail.com")
    b = await _profile(schema, "kavya.rao@gmail.com")
    emails = {a["institution_email"], b["institution_email"]}
    assert emails == {"kavya@lms.edu", "kavya2@lms.edu"}


# ===========================================================================
# Backfill (existing faculty) — admins untouched
# ===========================================================================

@pytest.mark.asyncio
async def test_backfill_existing_faculty(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    # Existing FACULTY with no profile/code/email, plus an ADMIN that must be left alone.
    fac_id, admin_id = uuid.uuid4(), uuid.uuid4()
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            await s.execute(text(
                "INSERT INTO users (id, email, password_hash, role, full_name, is_active) "
                "VALUES (:id, 'legacy@t.edu', 'x', 'FACULTY', 'Legacy Faculty', true)"
            ), {"id": str(fac_id)})
            await s.execute(text(
                "INSERT INTO users (id, email, password_hash, role, full_name, is_active) "
                "VALUES (:id, 'theadmin@t.edu', 'x', 'ADMIN', 'The Admin', true)"
            ), {"id": str(admin_id)})

    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            preview = await FacultyBackfillService.preview(s)
    assert preview.codes_to_assign == 1
    assert preview.emails_to_assign == 1

    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            result = await FacultyBackfillService.commit(s, actor_user_id=admin_id)
    assert result.codes_assigned == 1
    assert result.emails_assigned == 1
    assert result.profiles_created == 1

    prof = await _profile(schema, "legacy@t.edu")
    assert prof["faculty_code"] == "FAC0001"
    assert prof["institution_email"] == "legacy@lms.edu"  # first-name handle
    assert prof["personal_email"] == "legacy@t.edu"  # backfilled from login email

    # Admin completely untouched — no profile, no code, no institution email.
    admin_prof = await _profile(schema, "theadmin@t.edu")
    assert admin_prof["role"] == "ADMIN"
    assert admin_prof["faculty_code"] is None
    assert admin_prof["institution_email"] is None
    assert admin_prof["personal_email"] is None

    # Idempotent: a second commit assigns nothing more.
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            again = await FacultyBackfillService.commit(s, actor_user_id=admin_id)
    assert again.codes_assigned == 0
    assert again.emails_assigned == 0
