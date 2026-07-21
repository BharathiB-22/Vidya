from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import select, text

from app.database import AsyncSessionLocal, _tenant_schema_ctx
from app.modules.m01_program_advisor.models import Program, ProgramStatus
from app.modules.m01_program_advisor.schemas import CourseCreate, ProgramOutcomeCreate
from app.modules.m01_program_advisor.service import ProgramService
from tests.conftest import SCHEMA_A, SLUG_A, _insert_tenant_user


# ---------------------------------------------------------------------------
# DEAN user fixture (SCHEMA_A)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def dean_user_a(test_tenant_a):
    user = await _insert_tenant_user(SCHEMA_A, "dean_a@test.com", "Dean1234!", "DEAN", "Dean A")
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


# ---------------------------------------------------------------------------
# GOVERNANCE (BOARD) user fixtures — Phase A.
#
# Two of them, because the separation-of-duties rule needs two distinct people:
# the member who submits can never be the member who approves.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def board_user_a(test_tenant_a):
    user = await _insert_tenant_user(SCHEMA_A, "board_a@test.com", "Board1234!", "BOARD", "Board A")
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


@pytest_asyncio.fixture
async def board_user_a2(test_tenant_a):
    user = await _insert_tenant_user(SCHEMA_A, "board_a2@test.com", "Board1234!", "BOARD", "Board A2")
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


# ---------------------------------------------------------------------------
# Schema-aware DB session for service-layer tests.
#
# Uses the app's OWN mechanism — the `_tenant_schema_ctx` ContextVar, which the
# engine's "begin" event reads to inject `SET LOCAL search_path` at the start of
# every transaction (app/database.py).
#
# The previous approach — one session-level `SET search_path` at fixture setup —
# looked simpler but was quietly broken. Service methods commit, which ends the
# transaction and returns the connection to the pool; the next statement may check
# out a DIFFERENT connection, which never saw that SET. It happened to work when
# these tests ran alone (the pool handed back the same connection every time) and
# failed the moment another test file churned the pool first, with a baffling
# `relation "programs" does not exist`.
#
# Setting the ContextVar re-injects the search_path on every BEGIN, so it cannot
# be lost — which is exactly why the app does it this way.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def tenant_db_a(test_tenant_a):
    token = _tenant_schema_ctx.set(SCHEMA_A)
    try:
        async with AsyncSessionLocal() as session:
            yield session
    finally:
        _tenant_schema_ctx.reset(token)


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

async def force_status(program_id: uuid.UUID, status: ProgramStatus, tenant_db) -> None:
    """In-session status override for service tests (same open session, no extra commit).

    Mutates the ORM-mapped `Program` object directly (rather than raw SQL)
    so the change is visible to every other reference to that same
    identity-mapped instance in this session -- with `expire_on_commit=False`
    a raw `UPDATE ... WHERE` leaves any already-loaded `Program` object (e.g.
    the one `_create_draft` returned) showing its stale in-memory `.status`,
    since nothing ever expires it.
    """
    program = (
        await tenant_db.execute(select(Program).where(Program.id == program_id))
    ).scalar_one()
    program.status = status
    await tenant_db.flush()


async def force_status_committed(program_id: uuid.UUID, status: ProgramStatus) -> None:
    """Standalone status override that opens its own connection and commits.
    Required by router tests where the HTTP request uses a separate session."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            await session.execute(
                text("UPDATE programs SET status = :s WHERE id = :id"),
                {"s": status.value, "id": str(program_id)},
            )


# ---------------------------------------------------------------------------
# Payload factory
#
# Uses MSc (PG2 thresholds: min_total=60, min_sem=12, max_course_credits=6)
# so a small test fixture (4 sems × 3 courses × 5 credits = 60 total) is
# compliant without needing 32+ courses.
# ---------------------------------------------------------------------------

# The institutional programme every test curriculum belongs to.
#
# Not optional decoration: a course code is {PREFIX}{semester}{NN} and the PREFIX is
# `acad_programs.code`, so a curriculum with no programme has no code to number its
# courses under — add_course, add_choice and a semester move all refuse (422
# ACAD_PROGRAM_REQUIRED) rather than invent a prefix. Fixed IDs so the row is
# seeded once and every test's programme points at the same MSC.
ACAD_DEPT_ID_A    = uuid.UUID("11111111-1111-4111-8111-111111111111")
ACAD_PROGRAM_ID_A = uuid.UUID("22222222-2222-4222-8222-222222222222")
ACAD_PROGRAM_CODE = "MSC"


async def ensure_acad_program() -> uuid.UUID:
    """Seed the department + programme the test curricula are numbered under.

    Standalone session + commit, like force_status_committed: the router tests reach
    the API over HTTP on a session of their own and never touch `tenant_db_a`, so
    seeding inside that fixture would leave them with no programme to be numbered
    under. Idempotent — every test in the module shares this one MSC.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            await session.execute(
                text(
                    "INSERT INTO acad_departments (id, name, code, is_active) "
                    "VALUES (:id, 'Computer Science', 'CS', true) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"id": str(ACAD_DEPT_ID_A)},
            )
            await session.execute(
                text(
                    "INSERT INTO acad_programs "
                    "  (id, department_id, name, code, degree_type, duration_years, is_active) "
                    "VALUES (:id, :dept, 'M.Sc Computer Science', :code, 'PG', 2, true) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": str(ACAD_PROGRAM_ID_A),
                    "dept": str(ACAD_DEPT_ID_A),
                    "code": ACAD_PROGRAM_CODE,
                },
            )
    return ACAD_PROGRAM_ID_A


@pytest_asyncio.fixture(autouse=True)
async def _seed_acad_program(test_tenant_a):
    """Every m01 test gets the programme its curricula are numbered under, so no
    test can forget and fail on a 422 that has nothing to do with what it asserts."""
    await ensure_acad_program()


def make_program_payload(**overrides) -> dict:
    base = {
        "title": "M.Sc Computer Science",
        "degree_type": "MSc",
        "department": "Computer Science",
        "duration_years": 2,
        "total_credits": 60,
        # A str, not a UUID: this payload is both splatted into ProgramCreate (which
        # coerces it) and posted as JSON by the router tests (which cannot serialise
        # a UUID). See ensure_acad_program above for why every curriculum is linked.
        "acad_program_id": str(ACAD_PROGRAM_ID_A),
    }
    return {**base, **overrides}


async def build_compliant_program(program_id: uuid.UUID, tenant_db) -> None:
    """Add 3 outcomes + 12 courses that satisfy all MSc compliance rules, and
    bind the curriculum to a batch so it can be submitted.

    Layout: 4 semesters × 3 courses × 5 credits = 60 total.
    Electives: courses 3 and 6 → 2/12 = 16.7 % ≥ 15 % minimum.
    """
    for i in range(1, 4):
        await ProgramService.add_outcome(
            program_id,
            ProgramOutcomeCreate(code=f"PO{i}", description=f"Outcome {i}"),
            db=tenant_db,
        )

    idx = 1
    for sem in range(1, 5):
        for _ in range(3):
            await ProgramService.add_course(
                program_id,
                CourseCreate(
                    code=f"CS{idx:03d}",
                    title=f"Course {idx}",
                    credits=5,
                    semester=sem,
                    is_elective=(idx in (3, 6)),
                ),
                db=tenant_db,
            )
            idx += 1

    await bind_to_batch(program_id, tenant_db)


async def bind_to_batch(program_id: uuid.UUID, tenant_db) -> uuid.UUID:
    """Give the curriculum an Academic Year and a Batch. Returns the batch id.

    `submit_for_approval` requires both: an approved curriculum is immutable and
    students stay on the version they were admitted under, so which batch it
    governs cannot be answered after the fact.

    A batch hangs off an acad_program, which hangs off an acad_department, so the
    chain is built once and reused. Idempotent — many tests call this.
    """
    batch_id = (
        await tenant_db.execute(
            text("SELECT id FROM acad_batches WHERE name = 'Test Batch 2026-2028'")
        )
    ).scalar_one_or_none()

    if batch_id is None:
        dept_id = (
            await tenant_db.execute(
                text("SELECT id FROM acad_departments WHERE code = 'TCS'")
            )
        ).scalar_one_or_none()
        if dept_id is None:
            dept_id = uuid.uuid4()
            await tenant_db.execute(
                text(
                    "INSERT INTO acad_departments (id, name, code) "
                    "VALUES (:id, 'Test Computer Science', 'TCS')"
                ),
                {"id": str(dept_id)},
            )

        acad_program_id = (
            await tenant_db.execute(
                text("SELECT id FROM acad_programs WHERE code = 'TMSC'")
            )
        ).scalar_one_or_none()
        if acad_program_id is None:
            acad_program_id = uuid.uuid4()
            await tenant_db.execute(
                text(
                    "INSERT INTO acad_programs "
                    "(id, department_id, name, code, degree_type, duration_years) "
                    "VALUES (:id, :d, 'Test M.Sc CS', 'TMSC', 'PG', 2)"
                ),
                {"id": str(acad_program_id), "d": str(dept_id)},
            )

        batch_id = uuid.uuid4()
        await tenant_db.execute(
            text(
                "INSERT INTO acad_batches (id, program_id, name, start_year, end_year) "
                "VALUES (:id, :p, 'Test Batch 2026-2028', 2026, 2028)"
            ),
            {"id": str(batch_id), "p": str(acad_program_id)},
        )

    await tenant_db.execute(
        text(
            "UPDATE programs SET academic_year = '2026-2028', "
            "effective_from_batch_id = :b WHERE id = :id"
        ),
        {"b": str(batch_id), "id": str(program_id)},
    )
    await tenant_db.flush()
    return batch_id


async def bind_to_batch_committed(program_id: uuid.UUID) -> None:
    """`bind_to_batch` for router tests, which drive the app over HTTP and so use
    a different session from the test's own."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            await bind_to_batch(program_id, session)


async def approve_all_syllabi_committed(program_id: uuid.UUID, approved_by: uuid.UUID) -> int:
    """`approve_all_syllabi` for router tests."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            return await approve_all_syllabi(program_id, session, approved_by)


async def approve_all_syllabi(program_id: uuid.UUID, tenant_db, approved_by: uuid.UUID) -> int:
    """Give every subject in the curriculum an APPROVED official syllabus.

    The Board cannot approve a curriculum until every subject has one — that gate
    is the whole point of Phase A, so a test that wants to reach an APPROVED
    curriculum has to satisfy it. This is the shortcut: it writes the syllabi
    straight in rather than running forty AI generations.
    """
    course_ids = (
        await tenant_db.execute(
            text("SELECT id FROM courses WHERE program_id = :p"), {"p": str(program_id)},
        )
    ).scalars().all()

    for course_id in course_ids:
        # doc_type is NOT NULL since migration 0086ten (course-type intelligence):
        # a syllabus records WHICH document it is — a theory syllabus, a lab manual,
        # a project handbook. This helper predates that column and was still writing
        # rows without it, so every test that needed an approved curriculum died on a
        # NotNullViolation. Taken from the course, exactly as the migration's backfill
        # does; an untyped course reads as THEORY, which is what it was generated as.
        await tenant_db.execute(
            text(
                "INSERT INTO syllabi "
                "(id, course_id, version, status, doc_type, created_by_user_id, "
                " approved_by_user_id, approved_at, objectives, practical_components) "
                "SELECT :id, :c, 1, 'APPROVED', coalesce(c.course_type, 'THEORY'), "
                "       :u, :u, now(), '[]'::jsonb, '[]'::jsonb "
                "  FROM courses c WHERE c.id = :c"
            ),
            {"id": str(uuid.uuid4()), "c": str(course_id), "u": str(approved_by)},
        )
    await tenant_db.flush()
    return len(course_ids)
