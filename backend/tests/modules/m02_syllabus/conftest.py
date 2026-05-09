"""
Shared fixtures for M02 syllabus tests.

Schema layout
-------------
All tests run against SCHEMA_A (tenant_test_a).
M01 data (program + POs + course) is seeded in m01_setup because M02
syllabi reference M01 course IDs.

Session note
------------
tenant_db_a uses SET search_path (no LOCAL) so the path persists across
the multiple commits service methods make within a single test.
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
from app.modules.m02_syllabus.models import BloomLevel, SyllabusStatus
from app.modules.m02_syllabus.schemas import (
    CourseOutcomeCreate,
    SyllabusCreate,
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


# ---------------------------------------------------------------------------
# Schema-aware DB session for service-layer tests.
# SET search_path (no LOCAL) persists the path across auto-begin transactions.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def tenant_db_a(test_tenant_a):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET search_path = {SCHEMA_A}, public"))
        yield session


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
    """In-session status override (same open session, no extra commit)."""
    await tenant_db.execute(
        text("UPDATE syllabi SET status = :s WHERE id = :id"),
        {"s": status.value, "id": str(syllabus_id)},
    )


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
            db=tenant_db,
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
            db=tenant_db,
        )
