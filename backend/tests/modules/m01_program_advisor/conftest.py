from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import select, text

from app.database import AsyncSessionLocal
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
# Schema-aware DB session for service-layer tests.
#
# Uses SET search_path (without LOCAL) so the search_path survives across
# multiple commits inside a single session — service methods each call
# db.commit(), ending the current transaction; SET LOCAL would be lost.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def tenant_db_a(test_tenant_a):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET search_path = {SCHEMA_A}, public"))
        # search_path is now session-level; persists for subsequent auto-begin transactions
        yield session


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

def make_program_payload(**overrides) -> dict:
    base = {
        "title": "M.Sc Computer Science",
        "degree_type": "MSc",
        "department": "Computer Science",
        "duration_years": 2,
        "total_credits": 60,
    }
    return {**base, **overrides}


async def build_compliant_program(program_id: uuid.UUID, tenant_db) -> None:
    """Add 3 outcomes + 12 courses that satisfy all MSc compliance rules.

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
