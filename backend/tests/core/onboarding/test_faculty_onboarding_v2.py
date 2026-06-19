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


async def _dept(schema, email):
    """Return the profile's primary_department_id (as str) for a faculty email."""
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            r = await s.execute(text(
                "SELECT p.primary_department_id::text AS dept "
                "FROM users u JOIN sis_faculty_profiles p ON p.user_id = u.id "
                "WHERE LOWER(u.email) = :e"
            ), {"e": email.lower()})
            row = r.mappings().one_or_none()
            return row["dept"] if row else None


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
    # Kavya has no explicit primary → defaults to FACULTY, gets a code + grants.
    kavya = next(r for r in preview.rows if r.full_name == "Dr Kavya")
    assert kavya.primary_role == "FACULTY"
    assert kavya.projected_faculty_code == "FAC0001"
    assert kavya.projected_institution_email == "kavya@lms.edu"
    assert set(kavya.resolved_roles) == {"GUIDE", "EVALUATOR"}
    # DEAN is a primary role → standalone account, NO faculty code / grants.
    arun = next(r for r in preview.rows if r.full_name == "Dr Arun")
    assert arun.primary_role == "DEAN"
    assert arun.resolved_roles == []
    assert arun.projected_faculty_code is None
    # BOARD is a primary role → standalone account, NO faculty code / grants.
    meena = next(r for r in preview.rows if r.full_name == "Dr Meena")
    assert meena.primary_role == "BOARD"
    assert meena.resolved_roles == []
    assert meena.projected_faculty_code is None
    sm = preview.summary_meta
    assert sm["faculty_codes_to_assign"] == 1   # only Kavya (FACULTY)
    assert sm["new_role_grants"] == 2           # GUIDE + EVALUATOR (DEAN/BOARD primary)


@pytest.mark.asyncio
async def test_preview_unknown_role_warns(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    content = "full_name,personal_email,roles\nDr Z,z@gmail.com,HOD|GUIDE\n".encode()
    preview = await _preview(schema, content)
    row = preview.rows[0]
    assert row.primary_role == "FACULTY"        # no primary token → FACULTY default
    assert row.resolved_roles == ["GUIDE"]
    assert row.unresolved_roles == ["HOD"]
    assert any("HOD" in w for w in row.warnings)


@pytest.mark.asyncio
async def test_preview_rejects_responsibility_on_dean(test_tenant_a):
    """Example 7: roles=DEAN|GUIDE is invalid — DEAN is not a grant holder."""
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    content = "full_name,personal_email,roles\nDr D,d@gmail.com,DEAN|GUIDE\n".encode()
    preview = await _preview(schema, content)
    row = preview.rows[0]
    assert row.is_valid is False
    assert any("DEAN" in e and "GUIDE" in e for e in row.errors)


@pytest.mark.asyncio
async def test_preview_rejects_responsibility_on_board(test_tenant_a):
    """Example 8: roles=BOARD|GUIDE is invalid — BOARD is a primary role."""
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    content = "full_name,personal_email,roles\nDr B,b@gmail.com,BOARD|GUIDE\n".encode()
    preview = await _preview(schema, content)
    row = preview.rows[0]
    assert row.is_valid is False
    assert any("BOARD" in e for e in row.errors)


@pytest.mark.asyncio
async def test_preview_rejects_multiple_primary_roles(test_tenant_a):
    """Two primary roles in one row is ambiguous → invalid."""
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    content = "full_name,personal_email,roles\nDr M,m@gmail.com,DEAN|BOARD\n".encode()
    preview = await _preview(schema, content)
    row = preview.rows[0]
    assert row.is_valid is False
    assert any("primary role" in e.lower() for e in row.errors)


# ===========================================================================
# Commit
# ===========================================================================

@pytest.mark.asyncio
async def test_commit_creates_identity_programs_grants(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    admin = await _admin(schema)
    result = await _commit(schema, _CSV, admin)

    assert result.created == 3                     # FACULTY + DEAN + BOARD all created
    assert result.faculty_codes_assigned == 1      # only Kavya (FACULTY)
    assert result.faculty_institution_emails_assigned == 1
    assert result.program_mappings_created == 2    # Kavya BCA+MCA (DEAN/BOARD skipped)
    assert result.role_grants_created == 2         # GUIDE + EVALUATOR

    # Kavya → FACULTY workspace, with code, institution email and grants.
    kavya = await _profile(schema, "kavya@gmail.com")
    assert kavya["role"] == "FACULTY"
    assert kavya["email"] == "kavya@gmail.com"          # login identity = personal email
    assert kavya["personal_email"] == "kavya@gmail.com"
    assert kavya["faculty_code"] == "FAC0001"
    assert kavya["institution_email"] == "kavya@lms.edu"
    assert await _grants(schema, "kavya@gmail.com") == {"GUIDE", "EVALUATOR"}

    # Arun → DEAN workspace: primary role DEAN, NO faculty code / profile / grants.
    arun = await _profile(schema, "arun@yahoo.com")
    assert arun["role"] == "DEAN"
    assert arun["faculty_code"] is None
    assert arun["institution_email"] is None
    assert await _grants(schema, "arun@yahoo.com") == set()

    # Meena → BOARD workspace: primary role BOARD, NO faculty code / profile / grants.
    meena = await _profile(schema, "meena@gmail.com")
    assert meena["role"] == "BOARD"
    assert meena["faculty_code"] is None
    assert meena["institution_email"] is None
    assert await _grants(schema, "meena@gmail.com") == set()


@pytest.mark.asyncio
async def test_commit_explicit_faculty_responsibilities(test_tenant_a):
    """Examples 4 & 5: FACULTY|GUIDE and FACULTY|EVALUATOR → FACULTY + single grant."""
    schema = test_tenant_a["schema_name"]
    await _setup(schema)
    admin = await _admin(schema)
    content = (
        "full_name,personal_email,roles\n"
        "Faculty Guide,fg@gmail.com,FACULTY|GUIDE\n"
        "Faculty Evaluator,fe@gmail.com,FACULTY|EVALUATOR\n"
        "Plain Faculty,pf@gmail.com,FACULTY\n"
    ).encode()
    result = await _commit(schema, content, admin)

    assert result.created == 3
    assert result.faculty_codes_assigned == 3            # all three are FACULTY
    assert result.role_grants_created == 2               # one GUIDE + one EVALUATOR

    fg = await _profile(schema, "fg@gmail.com")
    assert fg["role"] == "FACULTY" and fg["faculty_code"] is not None
    assert await _grants(schema, "fg@gmail.com") == {"GUIDE"}
    assert await _grants(schema, "fe@gmail.com") == {"EVALUATOR"}
    assert await _grants(schema, "pf@gmail.com") == set()


# ===========================================================================
# Faculty Directory Option 1 — derive primary_department_id from program codes
# ===========================================================================

@pytest.mark.asyncio
async def test_commit_derives_primary_department_from_programs(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema)
    admin = await _admin(schema)
    # Only Kavya is FACULTY (with programs under dept "CA"); Arun=DEAN, Meena=BOARD
    # are standalone accounts with no profile, so no department is derived for them.
    result = await _commit(schema, _CSV, admin)

    assert result.faculty_primary_departments_derived == 1
    assert await _dept(schema, "kavya@gmail.com") == str(ids["dept"])
    assert await _dept(schema, "arun@yahoo.com") is None
    assert await _dept(schema, "meena@gmail.com") is None


@pytest.mark.asyncio
async def test_commit_does_not_overwrite_existing_department(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema)
    admin = await _admin(schema)
    # An existing FACULTY whose profile already has a (different) home department.
    other_dept = uuid.uuid4()
    fac_id = uuid.uuid4()
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            await s.execute(text(
                "INSERT INTO acad_departments (id, school_id, name, code, is_active) "
                "VALUES (:id, :sch, 'Mathematics', 'MA', true)"
            ), {"id": str(other_dept), "sch": str(ids["school"])})
            await s.execute(text(
                "INSERT INTO users (id, email, password_hash, role, full_name, is_active) "
                "VALUES (:id, 'pre@t.edu', 'x', 'FACULTY', 'Dr Pre', true)"
            ), {"id": str(fac_id)})
            await s.execute(text(
                "INSERT INTO sis_faculty_profiles "
                "(user_id, faculty_code, institution_email, primary_department_id, is_active, lifecycle_status) "
                "VALUES (:uid, 'FAC9999', 'pre@lms.edu', :dep, true, 'ACTIVE')"
            ), {"uid": str(fac_id), "dep": str(other_dept)})

    content = "full_name,personal_email,program_codes\nDr Pre,pre@t.edu,MCA\n".encode()
    result = await _commit(schema, content, admin)

    # MCA lives under dept CA, but the Dean-set Mathematics dept must survive.
    assert result.faculty_primary_departments_derived == 0
    assert await _dept(schema, "pre@t.edu") == str(other_dept)


@pytest.mark.asyncio
async def test_backfill_derives_department_for_existing_faculty(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema)
    admin = await _admin(schema)
    # Existing FACULTY with NO profile but an active program assignment (MCA → CA).
    fac_id = uuid.uuid4()
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            await s.execute(text(
                "INSERT INTO users (id, email, password_hash, role, full_name, is_active) "
                "VALUES (:id, 'leg2@t.edu', 'x', 'FACULTY', 'Legacy Two', true)"
            ), {"id": str(fac_id)})
            await s.execute(text(
                "INSERT INTO faculty_program_assignments "
                "(id, faculty_user_id, program_id, is_active, assigned_by) "
                "VALUES (:id, :f, :p, true, :by)"
            ), {"id": str(uuid.uuid4()), "f": str(fac_id), "p": str(ids["mca"]), "by": str(admin)})

    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            preview = await FacultyBackfillService.preview(s)
    assert preview.departments_to_derive == 1

    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            result = await FacultyBackfillService.commit(s, actor_user_id=admin)
    assert result.departments_derived == 1
    assert await _dept(schema, "leg2@t.edu") == str(ids["dept"])

    # Idempotent: a second pass derives nothing more.
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            again = await FacultyBackfillService.commit(s, actor_user_id=admin)
    assert again.departments_derived == 0


@pytest.mark.asyncio
async def test_backfill_does_not_overwrite_existing_department(test_tenant_a):
    schema = test_tenant_a["schema_name"]
    ids = await _setup(schema)
    admin = await _admin(schema)
    other_dept = uuid.uuid4()
    fac_id = uuid.uuid4()
    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            await s.execute(text(
                "INSERT INTO acad_departments (id, school_id, name, code, is_active) "
                "VALUES (:id, :sch, 'Physics', 'PH', true)"
            ), {"id": str(other_dept), "sch": str(ids["school"])})
            await s.execute(text(
                "INSERT INTO users (id, email, password_hash, role, full_name, is_active) "
                "VALUES (:id, 'leg3@t.edu', 'x', 'FACULTY', 'Legacy Three', true)"
            ), {"id": str(fac_id)})
            await s.execute(text(
                "INSERT INTO sis_faculty_profiles "
                "(user_id, faculty_code, institution_email, primary_department_id, is_active, lifecycle_status) "
                "VALUES (:uid, 'FAC8888', 'leg3@lms.edu', :dep, true, 'ACTIVE')"
            ), {"uid": str(fac_id), "dep": str(other_dept)})
            await s.execute(text(
                "INSERT INTO faculty_program_assignments "
                "(id, faculty_user_id, program_id, is_active, assigned_by) "
                "VALUES (:id, :f, :p, true, :by)"
            ), {"id": str(uuid.uuid4()), "f": str(fac_id), "p": str(ids["mca"]), "by": str(admin)})

    async with _Session() as s:
        async with s.begin():
            await s.execute(text(f"SET LOCAL search_path = {schema}, public"))
            preview = await FacultyBackfillService.preview(s)
            result = await FacultyBackfillService.commit(s, actor_user_id=admin)
    assert preview.departments_to_derive == 0
    assert result.departments_derived == 0
    assert await _dept(schema, "leg3@t.edu") == str(other_dept)


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
