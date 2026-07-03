"""
Shared fixtures for M03 course kit tests.

Schema layout
-------------
All tests run against SCHEMA_A (tenant_test_a).
M01 data (program + POs + course) is seeded via ProgramService.
M02 data (FACULTY_APPROVED syllabus with 4 units + 4 COs) is seeded via m02_setup.
M03 tests consume the approved syllabus to create course kits.

Session note
------------
tenant_db_a uses SET search_path (no LOCAL) so the path persists at the
connection level across the multiple commits service methods make within a
single test.
"""
from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.modules.m01_program_advisor.schemas import (
    CourseCreate,
    ProgramCreate,
    ProgramOutcomeCreate,
)
from app.modules.m01_program_advisor.service import ProgramService
from app.modules.m02_syllabus.models import BloomLevel as M02BloomLevel
from app.modules.m02_syllabus.schemas import (
    CourseOutcomeCreate,
    SyllabusCreate,
    SyllabusUnitCreate,
    UnitTopicItem,
)
from app.modules.m02_syllabus.service import SyllabusService
from app.modules.m03_course_kit.models import CourseKitStatus
from tests.conftest import SCHEMA_A, SLUG_A, _insert_tenant_user


# ---------------------------------------------------------------------------
# Extra role fixture: DEAN (M03 scope — separate email from M02 dean)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def dean_user_a(test_tenant_a):
    user = await _insert_tenant_user(
        SCHEMA_A, "dean_m03@test.com", "Dean1234!", "DEAN", "Dean M03"
    )
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


# ---------------------------------------------------------------------------
# Schema-aware DB session (SET search_path — session-level, persists across
# auto-begin transactions so service methods see the correct schema).
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def tenant_db_a(test_tenant_a):
    from app.database import _tenant_schema_ctx
    token = _tenant_schema_ctx.set(SCHEMA_A)
    try:
        async with AsyncSessionLocal() as session:
            yield session
    finally:
        _tenant_schema_ctx.reset(token)


# ---------------------------------------------------------------------------
# M02 seed: program + POs + course + FACULTY_APPROVED syllabus (4 COs, 4 units)
# Returns dict: {program_id, po_ids, course_id, syllabus_id}
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def m02_setup(test_tenant_a, tenant_db_a):
    program = await ProgramService.create_program(
        ProgramCreate(
            title="B.Tech Computer Science",
            degree_type="BTech",
            department="Computer Science",
            duration_years=4,
            total_credits=160,
        ),
        created_by=uuid.uuid4(),
        db=tenant_db_a,
    )

    po_ids = []
    for i in range(1, 4):
        po = await ProgramService.add_outcome(
            program.id,
            ProgramOutcomeCreate(code=f"PO{i}", description=f"Programme outcome {i}"),
            db=tenant_db_a,
        )
        po_ids.append(po.id)

    course = await ProgramService.add_course(
        program.id,
        CourseCreate(
            code="CS301",
            title="Data Structures and Algorithms",
            credits=4,
            semester=3,
        ),
        db=tenant_db_a,
    )

    syllabus = await SyllabusService.create_syllabus(
        SyllabusCreate(course_id=course.id),
        created_by=uuid.uuid4(),
        db=tenant_db_a,
    )

    bloom_levels = [
        M02BloomLevel.REMEMBER,
        M02BloomLevel.APPLY,
        M02BloomLevel.EVALUATE,
        M02BloomLevel.CREATE,
    ]
    for i, bl in enumerate(bloom_levels, 1):
        await SyllabusService.add_co(
            syllabus.id,
            CourseOutcomeCreate(
                code=f"CO{i}",
                description=f"Course outcome {i} description that is long enough",
                bloom_level=bl,
                display_order=i,
            ),
            db=tenant_db_a,
        )

    for i in range(1, 6):
        await SyllabusService.add_unit(
            syllabus.id,
            SyllabusUnitCreate(
                unit_number=i,
                title=f"Unit {i}: Topic Area",
                total_hours=12,
                topics=[UnitTopicItem(title=f"Topic {i}.1")],
            ),
            db=tenant_db_a,
        )

    # DRAFT → PENDING_REVIEW → DEAN_APPROVED (governance flow)
    await SyllabusService.submit_for_review(
        syllabus.id, submitted_by=uuid.uuid4(), db=tenant_db_a
    )
    approved = await SyllabusService.approve(
        syllabus.id, approved_by=uuid.uuid4(), db=tenant_db_a
    )

    yield {
        "program_id": program.id,
        "po_ids": po_ids,
        "course_id": course.id,
        "syllabus_id": approved.id,
    }


# ---------------------------------------------------------------------------
# DEAN program-scope grant (Phase 2 refinements — dean isolation).
#
# m02_setup's curriculum `programs` row has a NULL acad_program_id (created
# via ProgramService.create_program with no institutional linkage), so a
# DEAN caller governs it by default. This helper links it to a fresh
# acad_programs row and grants the given dean governance over it, matching
# what a real dean-scoped kit would look like.
# ---------------------------------------------------------------------------

async def grant_dean_program_scope(
    dean_user_id: uuid.UUID,
    program_id: uuid.UUID,
    schema_name: str,
) -> None:
    dept_id = uuid.uuid4()
    acad_prog_id = uuid.uuid4()
    suffix = str(acad_prog_id)[:8]

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {schema_name}, public"))
            await session.execute(text(
                "INSERT INTO acad_departments (id, name, code, is_active) "
                "VALUES (:id, :name, :code, true)"
            ), {"id": str(dept_id), "name": f"Dept {suffix}", "code": f"D{suffix[:7]}"})
            await session.execute(text(
                "INSERT INTO acad_programs "
                "(id, department_id, name, code, degree_type, duration_years, is_active) "
                "VALUES (:id, :dep, :name, :code, 'UG', 4, true)"
            ), {"id": str(acad_prog_id), "dep": str(dept_id), "name": "Scoped Program", "code": f"P{suffix[:7]}"})
            await session.execute(text(
                "UPDATE programs SET acad_program_id = :ap WHERE id = :pid"
            ), {"ap": str(acad_prog_id), "pid": str(program_id)})
            await session.execute(text(
                "INSERT INTO dean_program_assignments (dean_user_id, program_id, is_active, assigned_by) "
                "VALUES (:uid, :pid, true, :uid)"
            ), {"uid": str(dean_user_id), "pid": str(acad_prog_id)})


# ---------------------------------------------------------------------------
# Faculty course-assignment seeding (H-33 style assignment gate — mirrors
# tests/modules/m02_syllabus/test_router.py's _assign_faculty_to_course)
# ---------------------------------------------------------------------------

async def assign_faculty_to_course(
    course_id: uuid.UUID,
    faculty_user_id: uuid.UUID,
    schema_name: str,
) -> None:
    """Seed a minimal SubjectAssignment chain (dept->program->batch->semester->
    assignment) so the faculty passes the course-kit visibility/ownership gate."""
    dep_id  = uuid.uuid4()
    prog_id = uuid.uuid4()
    bat_id  = uuid.uuid4()
    sem_id  = uuid.uuid4()
    suffix  = str(dep_id)[:8]

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {schema_name}, public"))
            await session.execute(text(
                "INSERT INTO acad_departments (id, name, code, is_active) "
                "VALUES (:id, :name, :code, true)"
            ), {"id": str(dep_id), "name": f"Dept {suffix}", "code": f"D{suffix[:7]}"})
            await session.execute(text(
                "INSERT INTO acad_programs "
                "(id, department_id, name, code, degree_type, duration_years, is_active) "
                "VALUES (:id, :dep, :name, :code, 'UG', 4, true)"
            ), {"id": str(prog_id), "dep": str(dep_id), "name": "B.Tech Test", "code": f"P{suffix[:7]}"})
            await session.execute(text(
                "INSERT INTO acad_batches (id, program_id, name, start_year, end_year, is_active) "
                "VALUES (:id, :prog, :name, 2024, 2028, true)"
            ), {"id": str(bat_id), "prog": str(prog_id), "name": "Batch 2024"})
            await session.execute(text(
                "INSERT INTO acad_semesters (id, batch_id, number, is_active) "
                "VALUES (:id, :bat, 1, true)"
            ), {"id": str(sem_id), "bat": str(bat_id)})
            await session.execute(text(
                "INSERT INTO subject_assignments "
                "(id, course_id, faculty_user_id, semester_id, assigned_by_user_id, is_active, role_in_course) "
                "VALUES (:id, :course, :faculty, :sem, :by, true, 'PRIMARY')"
            ), {
                "id":      str(uuid.uuid4()),
                "course":  str(course_id),
                "faculty": str(faculty_user_id),
                "sem":     str(sem_id),
                "by":      str(uuid.uuid4()),
            })


# ---------------------------------------------------------------------------
# Status override helpers
# ---------------------------------------------------------------------------

async def force_kit_status(
    kit_id: uuid.UUID,
    status: CourseKitStatus,
    tenant_db,
) -> None:
    """In-session status override (same open session, no extra commit).

    Uses synchronize_session='evaluate' so SQLAlchemy updates the identity
    map in-place, preventing stale-cache reads in the same session.
    """
    from sqlalchemy import update as sa_update
    from app.modules.m03_course_kit.models import CourseKit as _CourseKit

    stmt = (
        sa_update(_CourseKit)
        .where(_CourseKit.id == kit_id)
        .values(status=status)
        .execution_options(synchronize_session="evaluate")
    )
    await tenant_db.execute(stmt)


async def force_kit_status_committed(
    kit_id: uuid.UUID,
    status: CourseKitStatus,
) -> None:
    """Standalone status override that commits in its own session.

    Required by router tests where the HTTP call uses a separate DB connection.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            await session.execute(
                text("UPDATE course_kits SET status = :s WHERE id = :id"),
                {"s": status.value, "id": str(kit_id)},
            )


# ---------------------------------------------------------------------------
# Payload factories
# ---------------------------------------------------------------------------

def make_kit_payload(syllabus_id: uuid.UUID, **overrides) -> dict:
    return {"syllabus_id": str(syllabus_id), "unit_number": 1, **overrides}


# ---------------------------------------------------------------------------
# Compliant kit seeder (10 slides + teaching_plan)
# ---------------------------------------------------------------------------

async def build_compliant_kit_via_db(
    kit_id: uuid.UUID,
    schema_name: str,
) -> None:
    """Seed 10 slides and a teaching_plan into a kit.

    Uses a standalone committed session so the data is visible to the HTTP
    layer (separate connection) in router tests.  SET search_path (no LOCAL)
    persists at the connection level across the service commits.
    """
    from app.modules.m03_course_kit.repository import CourseKitRepository
    from app.modules.m03_course_kit.schemas import (
        KitSlideCreate,
        SlideContent,
    )
    from app.modules.m03_course_kit.service import CourseKitService

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET search_path = {schema_name}, public"))

        for i in range(1, 11):
            await CourseKitService.add_slide(
                kit_id,
                KitSlideCreate(
                    slide_number=i,
                    title=f"Slide {i}: Core Concept",
                    content=SlideContent(
                        bullets=[f"Key point {i}.1", f"Key point {i}.2"],
                    ),
                    speaker_notes=f"Faculty notes for slide {i}.",
                ),
                db=session,
            )

        kit = await CourseKitRepository.get_by_id(kit_id, db=session)
        kit.teaching_plan = [
            {
                "week": 1,
                "topic": "Introduction",
                "objectives": ["Understand fundamentals"],
                "activities": ["Lecture", "Discussion"],
                "hours": 3,
                "co_references": ["CO1"],
            }
        ]
        await session.commit()
