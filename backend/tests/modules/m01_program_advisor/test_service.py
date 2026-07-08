"""
Service-layer tests for M01 ProgramService.
Uses a real DB session (tenant_db_a) with search_path set to SCHEMA_A.
"""
from __future__ import annotations

import uuid

import pytest

from app.modules.m01_program_advisor.models import ProgramStatus
from app.modules.m01_program_advisor.repository import ProgramRepository
from app.modules.m01_program_advisor.schemas import (
    CourseCreate,
    ElectiveBasketCreate,
    ProgramCreate,
    ProgramOutcomeCreate,
    ProgramUpdate,
)
from app.modules.m01_program_advisor.service import ProgramService, ProgramServiceError
from tests.modules.m01_program_advisor.conftest import (
    build_compliant_program,
    force_status,
    make_program_payload,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_draft(tenant_db, created_by: uuid.UUID | None = None):
    payload = ProgramCreate(**make_program_payload())
    return await ProgramService.create_program(
        payload,
        created_by=created_by or uuid.uuid4(),
        db=tenant_db,
    )


# ---------------------------------------------------------------------------
# Program CRUD
# ---------------------------------------------------------------------------

async def test_create_program_creates_draft(tenant_db_a):
    program = await _create_draft(tenant_db_a)
    assert program.status == ProgramStatus.DRAFT
    assert program.version == 1
    assert program.parent_version_id is None


async def test_update_requires_draft(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.PENDING_APPROVAL, tenant_db_a)

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.update_program(
            program.id,
            ProgramUpdate(title="New Title"),
            db=tenant_db_a,
        )
    assert exc.value.code == "INVALID_STATUS"


async def test_delete_allowed_when_approved(tenant_db_a, admin_user_a):
    # Phase 4.2: Approved programs remain editable/deletable until Published.
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.APPROVED, tenant_db_a)

    await ProgramService.delete_program(program.id, db=tenant_db_a)
    assert await ProgramRepository.get_by_id(program.id, db=tenant_db_a) is None


async def test_delete_blocked_when_published(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.PUBLISHED, tenant_db_a)

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.delete_program(program.id, db=tenant_db_a)
    assert exc.value.code == "INVALID_STATUS"


async def test_update_allowed_when_approved(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.APPROVED, tenant_db_a)

    updated = await ProgramService.update_program(
        program.id, ProgramUpdate(title="New Title"), db=tenant_db_a,
    )
    assert updated.title == "New Title"


async def test_update_blocked_when_published(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.PUBLISHED, tenant_db_a)

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.update_program(
            program.id, ProgramUpdate(title="New Title"), db=tenant_db_a,
        )
    assert exc.value.code == "INVALID_STATUS"


async def test_publish_requires_approved(tenant_db_a, admin_user_a, dean_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.publish(program.id, published_by=dean_user_a["id"], db=tenant_db_a)
    assert exc.value.code == "INVALID_STATUS"


async def test_publish_locks_program(tenant_db_a, admin_user_a, dean_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.APPROVED, tenant_db_a)

    published = await ProgramService.publish(program.id, published_by=dean_user_a["id"], db=tenant_db_a)
    assert published.status == ProgramStatus.PUBLISHED
    assert published.published_by_user_id == dean_user_a["id"]

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.delete_program(program.id, db=tenant_db_a)
    assert exc.value.code == "INVALID_STATUS"


# ---------------------------------------------------------------------------
# State machine: approve / reject
# ---------------------------------------------------------------------------

async def test_approve_requires_pending_approval(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    # Program is DRAFT, not PENDING_APPROVAL
    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.approve(program.id, approved_by=admin_user_a["id"], db=tenant_db_a)
    assert exc.value.code == "INVALID_STATUS"


async def test_reject_resets_to_draft(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.PENDING_APPROVAL, tenant_db_a)

    updated = await ProgramService.reject(program.id, db=tenant_db_a)
    assert updated.status == ProgramStatus.DRAFT


async def test_approve_compliant_program(tenant_db_a, admin_user_a, dean_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await build_compliant_program(program.id, tenant_db_a)
    await force_status(program.id, ProgramStatus.PENDING_APPROVAL, tenant_db_a)

    approved = await ProgramService.approve(
        program.id, approved_by=dean_user_a["id"], db=tenant_db_a
    )
    assert approved.status == ProgramStatus.APPROVED
    assert approved.approved_by_user_id == dean_user_a["id"]


async def test_approve_compliance_gate_blocks(tenant_db_a, admin_user_a, dean_user_a):
    # Program with 0 outcomes and 0 courses fails multiple rules.
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.PENDING_APPROVAL, tenant_db_a)

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.approve(
            program.id, approved_by=dean_user_a["id"], db=tenant_db_a
        )
    assert exc.value.code == "COMPLIANCE_FAILED"


# ---------------------------------------------------------------------------
# Fork
# ---------------------------------------------------------------------------

async def test_fork_requires_approved(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.fork_program(program.id, created_by=admin_user_a["id"], db=tenant_db_a)
    assert exc.value.code == "INVALID_STATUS"


async def test_fork_creates_new_version(tenant_db_a, admin_user_a, dean_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await build_compliant_program(program.id, tenant_db_a)
    await force_status(program.id, ProgramStatus.PENDING_APPROVAL, tenant_db_a)
    await ProgramService.approve(program.id, approved_by=dean_user_a["id"], db=tenant_db_a)

    forked = await ProgramService.fork_program(
        program.id, created_by=admin_user_a["id"], db=tenant_db_a
    )
    assert forked.version == 2
    assert forked.parent_version_id == program.id
    assert forked.status == ProgramStatus.DRAFT


# ---------------------------------------------------------------------------
# Immutability guards on courses and outcomes
# ---------------------------------------------------------------------------

async def test_add_course_requires_draft(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.APPROVED, tenant_db_a)

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.add_course(
            program.id,
            CourseCreate(code="CS001", title="Course", credits=4, semester=1, is_elective=False),
            db=tenant_db_a,
        )
    assert exc.value.code == "INVALID_STATUS"


async def test_add_outcome_requires_draft(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await force_status(program.id, ProgramStatus.APPROVED, tenant_db_a)

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.add_outcome(
            program.id,
            ProgramOutcomeCreate(code="PO1", description="desc"),
            db=tenant_db_a,
        )
    assert exc.value.code == "INVALID_STATUS"


async def test_duplicate_course_code_rejected(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    course = CourseCreate(code="CS101", title="Course", credits=4, semester=1, is_elective=False)
    await ProgramService.add_course(program.id, course, db=tenant_db_a)

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.add_course(program.id, course, db=tenant_db_a)
    assert exc.value.code == "CODE_EXISTS"


# ---------------------------------------------------------------------------
# Elective Baskets — an elective is never modeled as a single course; it
# must belong to a named basket alongside its sibling alternatives.
# ---------------------------------------------------------------------------

async def test_add_basket_and_course_becomes_elective(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    basket = await ProgramService.add_basket(
        program.id,
        ElectiveBasketCreate(semester=3, name="Artificial Intelligence Electives"),
        admin_user_a["id"],
        db=tenant_db_a,
    )
    assert basket.semester == 3

    course = await ProgramService.add_course(
        program.id,
        CourseCreate(
            code="AI301", title="Artificial Intelligence", credits=4, semester=3,
            is_elective=False, elective_basket_id=basket.id,
        ),
        db=tenant_db_a,
    )
    # A course inside a basket is an elective by definition, regardless of
    # what is_elective was explicitly passed as.
    assert course.is_elective is True
    assert course.elective_basket_id == basket.id


async def test_add_course_basket_semester_mismatch_rejected(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    basket = await ProgramService.add_basket(
        program.id, ElectiveBasketCreate(semester=3, name="AI Electives"),
        admin_user_a["id"], db=tenant_db_a,
    )

    with pytest.raises(ProgramServiceError) as exc:
        await ProgramService.add_course(
            program.id,
            CourseCreate(
                code="AI401", title="Deep Learning", credits=4, semester=4,
                elective_basket_id=basket.id,
            ),
            db=tenant_db_a,
        )
    assert exc.value.code == "BASKET_SEMESTER_MISMATCH"


async def test_delete_basket_unlinks_courses(tenant_db_a, admin_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    basket = await ProgramService.add_basket(
        program.id, ElectiveBasketCreate(semester=3, name="AI Electives"),
        admin_user_a["id"], db=tenant_db_a,
    )
    course = await ProgramService.add_course(
        program.id,
        CourseCreate(code="AI301", title="Artificial Intelligence", credits=4, semester=3, elective_basket_id=basket.id),
        db=tenant_db_a,
    )

    await ProgramService.delete_basket(basket.id, program.id, db=tenant_db_a)

    # The DELETE is raw SQL (bypasses the ORM unit-of-work), so `course` --
    # already loaded into this session's identity map above -- keeps its
    # stale in-memory elective_basket_id unless explicitly refreshed (see
    # the identical force_status staleness issue elsewhere in this suite).
    await tenant_db_a.refresh(course)
    assert course.elective_basket_id is None
    # is_elective is untouched by unlinking -- Dean may still want it flagged
    # elective while deciding which basket it belongs to next.
    assert course.is_elective is True


async def test_fork_program_copies_baskets_and_relinks_courses(tenant_db_a, admin_user_a, dean_user_a):
    program = await _create_draft(tenant_db_a, admin_user_a["id"])
    await build_compliant_program(program.id, tenant_db_a)
    basket = await ProgramService.add_basket(
        program.id, ElectiveBasketCreate(semester=3, name="AI Electives"),
        admin_user_a["id"], db=tenant_db_a,
    )
    await ProgramService.add_course(
        program.id,
        CourseCreate(code="AI301", title="Artificial Intelligence", credits=4, semester=3, elective_basket_id=basket.id),
        db=tenant_db_a,
    )
    await force_status(program.id, ProgramStatus.PENDING_APPROVAL, tenant_db_a)
    await ProgramService.approve(program.id, approved_by=dean_user_a["id"], db=tenant_db_a)

    forked = await ProgramService.fork_program(program.id, created_by=admin_user_a["id"], db=tenant_db_a)

    forked_baskets = await ProgramService.list_baskets(forked.id, db=tenant_db_a)
    assert len(forked_baskets) == 1
    assert forked_baskets[0].id != basket.id
    assert forked_baskets[0].name == "AI Electives"

    from app.modules.m01_program_advisor.repository import CourseRepository
    forked_courses = await CourseRepository.list_by_program(forked.id, db=tenant_db_a)
    forked_ai_course = next(c for c in forked_courses if c.code == "AI301")
    assert forked_ai_course.elective_basket_id == forked_baskets[0].id
