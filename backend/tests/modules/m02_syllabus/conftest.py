"""
Shared fixtures for M02 syllabus tests.

Schema layout
-------------
All tests run against SCHEMA_A (tenant_test_a).
M01 data (program + POs + course) is seeded in m01_setup because M02
syllabi reference M01 course IDs.

Session note
------------
tenant_db_a sets the app's `_tenant_schema_ctx` ContextVar rather than issuing a
session-level SET search_path — see the fixture for why the latter is unsafe.
"""
from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import text

from app.database import AsyncSessionLocal, _tenant_schema_ctx
from app.modules.m01_program_advisor.schemas import (
    CourseCreate,
    ProgramCreate,
    ProgramOutcomeCreate,
)
from app.modules.m01_program_advisor.service import ProgramService
from app.modules.m02_syllabus.models import BloomLevel, SyllabusStatus
from app.modules.m02_syllabus.schemas import (
    CourseOutcomeCreate,
    SyllabusUnitCreate,
    UnitTopicItem,
)
from app.modules.m02_syllabus.service import SyllabusService
from tests.conftest import SCHEMA_A, SLUG_A, _insert_tenant_user


# ---------------------------------------------------------------------------
# Extra role fixture: DEAN
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def dean_user_a(test_tenant_a):
    user = await _insert_tenant_user(SCHEMA_A, "dean_a2@test.com", "Dean1234!", "DEAN", "Dean A2")
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


# Phase A: the governance authority (Board / University Members) owns the
# syllabus — it writes, approves and locks it.
@pytest_asyncio.fixture
async def board_user_a(test_tenant_a):
    user = await _insert_tenant_user(SCHEMA_A, "board_a3@test.com", "Board1234!", "BOARD", "Board A3")
    yield {**user, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}


# ---------------------------------------------------------------------------
# Schema-aware DB session for service-layer tests.
#
# Uses the app's own `_tenant_schema_ctx` ContextVar, which the engine's "begin"
# event reads to inject `SET LOCAL search_path` at the start of EVERY transaction
# (app/database.py). A single session-level `SET search_path` at fixture setup is
# not enough: a service method's commit returns the connection to the pool, and
# the next statement may check out a different one that never saw it. See the
# same fixture in tests/modules/m01_program_advisor/conftest.py.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def tenant_db_a(test_tenant_a):
    token = _tenant_schema_ctx.set(SCHEMA_A)
    try:
        async with AsyncSessionLocal() as session:
            try:
                yield session
            finally:
                await session.rollback()
    finally:
        _tenant_schema_ctx.reset(token)


# ---------------------------------------------------------------------------
# M01 seed: program + 3 POs + 1 course
# Returns dict: {program_id, po_ids: [UUID, UUID, UUID], course_id}
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def m01_setup(test_tenant_a, tenant_db_a):
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

    yield {"program_id": program.id, "po_ids": po_ids, "course_id": course.id}


# ---------------------------------------------------------------------------
# Status override helpers
# ---------------------------------------------------------------------------

async def force_syllabus_status(
    syllabus_id: uuid.UUID,
    status: SyllabusStatus,
    tenant_db,
) -> None:
    """In-session status override (same open session, no extra commit).

    Uses ORM UPDATE with synchronize_session='evaluate' so SQLAlchemy updates
    the identity map in-place. Raw text() UPDATE would leave a stale cached
    object and the next service SELECT would read the wrong status.
    """
    from sqlalchemy import update as sa_update
    from app.modules.m02_syllabus.models import Syllabus as _Syllabus

    stmt = (
        sa_update(_Syllabus)
        .where(_Syllabus.id == syllabus_id)
        .values(status=status)
        .execution_options(synchronize_session="evaluate")
    )
    await tenant_db.execute(stmt)


async def force_syllabus_status_committed(
    syllabus_id: uuid.UUID,
    status: SyllabusStatus,
) -> None:
    """Standalone status override that commits in its own session.
    Required by router tests where the HTTP call uses a separate connection."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {SCHEMA_A}, public"))
            await session.execute(
                text("UPDATE syllabi SET status = :s WHERE id = :id"),
                {"s": status.value, "id": str(syllabus_id)},
            )


# ---------------------------------------------------------------------------
# Payload factories
# ---------------------------------------------------------------------------

def make_syllabus_payload(course_id: uuid.UUID, **overrides) -> dict:
    return {"course_id": str(course_id), **overrides}


async def build_compliant_syllabus(
    syllabus_id: uuid.UUID,
    tenant_db,
) -> None:
    """Add 4 COs (different Bloom levels) + 4 units to satisfy all compliance rules."""
    bloom_levels = [BloomLevel.REMEMBER, BloomLevel.APPLY, BloomLevel.EVALUATE, BloomLevel.CREATE]
    for i, bl in enumerate(bloom_levels, 1):
        await SyllabusService.add_co(
            syllabus_id,
            CourseOutcomeCreate(
                code=f"CO{i}",
                description=f"Course outcome {i} description that is long enough",
                bloom_level=bl,
                display_order=i,
            ),
            caller_role="BOARD", db=tenant_db,
        )

    for i in range(1, 5):
        await SyllabusService.add_unit(
            syllabus_id,
            SyllabusUnitCreate(
                unit_number=i,
                title=f"Unit {i}: Topic Area",
                total_hours=12,
                topics=[UnitTopicItem(title=f"Topic {i}.1")],
            ),
            caller_role="BOARD", db=tenant_db,
        )
