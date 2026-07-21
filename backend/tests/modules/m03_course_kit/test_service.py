"""
Service-layer integration tests for M03 CourseKitService.
Uses a real DB session (tenant_db_a) with search_path set to SCHEMA_A.
Celery dispatch is mocked to avoid Redis/broker dependency.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.modules.m03_course_kit.models import CourseKitStatus
from app.modules.m03_course_kit.schemas import (
    AssignmentType,
    CourseKitCreate,
    CourseKitUpdate,
    KitAssignmentCreate,
    KitSlideCreate,
    KitSlideUpdate,
    RubricCriterion,
    SlideContent,
)
from app.modules.m03_course_kit.service import CourseKitService, KitServiceError
from tests.modules.m03_course_kit.conftest import (
    build_compliant_kit_via_db,
    force_kit_status,
    make_kit_payload,
)


# ---------------------------------------------------------------------------
# Helper: create a DRAFT kit
# ---------------------------------------------------------------------------

async def _create_draft(tenant_db, syllabus_id: uuid.UUID, unit_number: int = 1) -> object:
    return await CourseKitService.create_kit(
        CourseKitCreate(**make_kit_payload(syllabus_id, unit_number=unit_number)),
        created_by=uuid.uuid4(),
        db=tenant_db,
    )


# ===========================================================================
# CRUD
# ===========================================================================

async def test_create_kit_creates_draft(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    assert kit.status == CourseKitStatus.DRAFT
    assert kit.version == 1
    assert kit.parent_version_id is None
    assert kit.syllabus_id == m02_setup["syllabus_id"]


async def test_create_kit_blocked_for_unapproved_syllabus(tenant_db_a, m02_setup):
    from app.modules.m02_syllabus.models import SyllabusStatus
    from sqlalchemy import update as sa_update
    from app.modules.m02_syllabus.models import Syllabus as _Syllabus

    stmt = (
        sa_update(_Syllabus)
        .where(_Syllabus.id == m02_setup["syllabus_id"])
        .values(status=SyllabusStatus.DRAFT)
        .execution_options(synchronize_session="evaluate")
    )
    await tenant_db_a.execute(stmt)

    with pytest.raises(KitServiceError) as exc:
        await CourseKitService.create_kit(
            CourseKitCreate(**make_kit_payload(m02_setup["syllabus_id"])),
            created_by=uuid.uuid4(),
            db=tenant_db_a,
        )
    assert exc.value.code == "SYLLABUS_NOT_APPROVED"
    assert exc.value.status_code == 422


async def test_get_kit_returns_none_for_unknown_id(tenant_db_a, m02_setup):
    result = await CourseKitService.get_kit(uuid.uuid4(), db=tenant_db_a)
    assert result is None


async def test_list_kits_filters_by_syllabus_id(tenant_db_a, m02_setup):
    await _create_draft(tenant_db_a, m02_setup["syllabus_id"], unit_number=1)
    await _create_draft(tenant_db_a, m02_setup["syllabus_id"], unit_number=2)

    total, items = await CourseKitService.list_kits(
        m02_setup["syllabus_id"], db=tenant_db_a
    )
    assert total == 2
    assert all(k.syllabus_id == m02_setup["syllabus_id"] for k in items)


async def test_update_kit_allowed_in_draft(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    updated = await CourseKitService.update_kit(
        kit.id, CourseKitUpdate(tone="formal"), db=tenant_db_a
    )
    assert updated.tone == "formal"


async def test_update_kit_blocked_when_ai_generating(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    await force_kit_status(kit.id, CourseKitStatus.AI_GENERATING, tenant_db_a)

    with pytest.raises(KitServiceError) as exc:
        await CourseKitService.update_kit(
            kit.id, CourseKitUpdate(tone="changed"), db=tenant_db_a
        )
    assert exc.value.code == "GENERATING"
    assert exc.value.status_code == 409


async def test_update_kit_blocked_when_published(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    await force_kit_status(kit.id, CourseKitStatus.PUBLISHED, tenant_db_a)

    with pytest.raises(KitServiceError) as exc:
        await CourseKitService.update_kit(
            kit.id, CourseKitUpdate(tone="changed"), db=tenant_db_a
        )
    assert exc.value.code == "IMMUTABLE"
    assert exc.value.status_code == 409


async def test_delete_kit_allowed_on_draft(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    await CourseKitService.delete_kit(kit.id, db=tenant_db_a)
    assert await CourseKitService.get_kit(kit.id, db=tenant_db_a) is None


async def test_delete_kit_blocked_when_published(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    await force_kit_status(kit.id, CourseKitStatus.PUBLISHED, tenant_db_a)

    with pytest.raises(KitServiceError) as exc:
        await CourseKitService.delete_kit(kit.id, db=tenant_db_a)
    assert exc.value.code == "IMMUTABLE"


# ===========================================================================
# Generation dispatch
# ===========================================================================

async def test_dispatch_generation_transitions_to_ai_generating(
    tenant_db_a, m02_setup, test_tenant_a
):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])

    with patch(
        "app.workers.heavy.course_kit_generation.generate_course_kit"
    ) as mock_task:
        mock_task.delay = MagicMock(return_value=None)
        job_id = await CourseKitService.dispatch_kit_generation(
            kit_id=kit.id,
            tenant_id=test_tenant_a["id"],
            schema_name=test_tenant_a["schema_name"],
            db=tenant_db_a,
        )

    assert job_id is not None
    refreshed = await CourseKitService.get_kit(kit.id, db=tenant_db_a)
    assert refreshed.status == CourseKitStatus.AI_GENERATING


async def test_dispatch_generation_blocked_when_already_generating(
    tenant_db_a, m02_setup, test_tenant_a
):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    await force_kit_status(kit.id, CourseKitStatus.AI_GENERATING, tenant_db_a)

    with pytest.raises(KitServiceError) as exc:
        await CourseKitService.dispatch_kit_generation(
            kit_id=kit.id,
            tenant_id=test_tenant_a["id"],
            schema_name=test_tenant_a["schema_name"],
            db=tenant_db_a,
        )
    assert exc.value.code == "INVALID_STATE"
    assert exc.value.status_code == 409


# ===========================================================================
# Publish
# ===========================================================================

async def test_publish_compliant_kit_transitions_to_published(
    tenant_db_a, m02_setup, test_tenant_a
):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    await build_compliant_kit_via_db(kit.id, test_tenant_a["schema_name"])

    published = await CourseKitService.publish_kit(
        kit.id, published_by=uuid.uuid4(), db=tenant_db_a
    )
    assert published.status == CourseKitStatus.PUBLISHED
    assert published.published_at is not None


async def test_publish_blocked_when_slide_min_not_met(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])

    with pytest.raises(KitServiceError) as exc:
        await CourseKitService.publish_kit(
            kit.id, published_by=uuid.uuid4(), db=tenant_db_a
        )
    assert exc.value.code == "COMPLIANCE_FAILED"
    assert exc.value.status_code == 422


async def test_publish_blocked_on_non_draft_status(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    await force_kit_status(kit.id, CourseKitStatus.ARCHIVED, tenant_db_a)

    with pytest.raises(KitServiceError) as exc:
        await CourseKitService.publish_kit(
            kit.id, published_by=uuid.uuid4(), db=tenant_db_a
        )
    assert exc.value.code == "INVALID_STATE"


async def test_one_published_per_unit_invariant(
    tenant_db_a, m02_setup, test_tenant_a
):
    kit1 = await _create_draft(tenant_db_a, m02_setup["syllabus_id"], unit_number=3)
    await build_compliant_kit_via_db(kit1.id, test_tenant_a["schema_name"])
    await CourseKitService.publish_kit(kit1.id, published_by=uuid.uuid4(), db=tenant_db_a)

    kit2 = await _create_draft(tenant_db_a, m02_setup["syllabus_id"], unit_number=3)
    await build_compliant_kit_via_db(kit2.id, test_tenant_a["schema_name"])

    with pytest.raises(KitServiceError) as exc:
        await CourseKitService.publish_kit(
            kit2.id, published_by=uuid.uuid4(), db=tenant_db_a
        )
    assert exc.value.code == "UNIT_ALREADY_PUBLISHED"
    assert exc.value.status_code == 409


# ===========================================================================
# Archive
# ===========================================================================

async def test_archive_kit_transitions_from_published(
    tenant_db_a, m02_setup, test_tenant_a
):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    await build_compliant_kit_via_db(kit.id, test_tenant_a["schema_name"])
    await CourseKitService.publish_kit(kit.id, published_by=uuid.uuid4(), db=tenant_db_a)

    archived = await CourseKitService.archive_kit(kit.id, db=tenant_db_a)
    assert archived.status == CourseKitStatus.ARCHIVED


async def test_archive_blocked_when_draft(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])

    with pytest.raises(KitServiceError) as exc:
        await CourseKitService.archive_kit(kit.id, db=tenant_db_a)
    assert exc.value.code == "INVALID_STATE"
    assert exc.value.status_code == 409


# ===========================================================================
# Fork
# ===========================================================================

async def test_fork_creates_new_draft_with_parent_link(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])

    forked = await CourseKitService.fork_kit(
        kit.id, forked_by=uuid.uuid4(), change_note="Revised version", db=tenant_db_a
    )
    assert forked.status == CourseKitStatus.DRAFT
    assert forked.parent_version_id == kit.id
    assert forked.version == 2


async def test_fork_deep_copies_slides_with_speaker_notes(
    tenant_db_a, m02_setup, test_tenant_a
):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    await build_compliant_kit_via_db(kit.id, test_tenant_a["schema_name"])

    forked = await CourseKitService.fork_kit(
        kit.id, forked_by=uuid.uuid4(), change_note=None, db=tenant_db_a
    )

    orig_slides   = await CourseKitService.list_slides(kit.id, db=tenant_db_a)
    forked_slides = await CourseKitService.list_slides(forked.id, db=tenant_db_a)

    assert len(forked_slides) == len(orig_slides)
    assert forked_slides[0].title == orig_slides[0].title
    assert forked_slides[0].speaker_notes == orig_slides[0].speaker_notes


async def test_fork_blocked_when_ai_generating(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    await force_kit_status(kit.id, CourseKitStatus.AI_GENERATING, tenant_db_a)

    with pytest.raises(KitServiceError) as exc:
        await CourseKitService.fork_kit(
            kit.id, forked_by=uuid.uuid4(), change_note=None, db=tenant_db_a
        )
    assert exc.value.code == "GENERATING"
    assert exc.value.status_code == 409


# ===========================================================================
# Compliance check
# ===========================================================================

async def test_compliance_check_fails_on_empty_kit(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    result = await CourseKitService.run_compliance_check(kit.id, db=tenant_db_a)
    assert result.passed is False
    codes = {v.code for v in result.violations}
    assert "SLIDE_MIN_NOT_MET" in codes


async def test_compliance_check_passes_on_compliant_kit(
    tenant_db_a, m02_setup, test_tenant_a
):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    await build_compliant_kit_via_db(kit.id, test_tenant_a["schema_name"])

    result = await CourseKitService.run_compliance_check(kit.id, db=tenant_db_a)
    assert result.passed is True


# ===========================================================================
# Slides
# ===========================================================================

async def test_add_slide_succeeds_in_draft(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    slide = await CourseKitService.add_slide(
        kit.id,
        KitSlideCreate(
            slide_number=1,
            title="Introduction to Data Structures",
            content=SlideContent(bullets=["Arrays", "Linked Lists"]),
            speaker_notes="Introduce the fundamental data structure types.",
        ),
        db=tenant_db_a,
    )
    assert slide.slide_number == 1
    assert slide.title == "Introduction to Data Structures"
    assert slide.speaker_notes == "Introduce the fundamental data structure types."


async def test_add_slide_blocked_when_published(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    await force_kit_status(kit.id, CourseKitStatus.PUBLISHED, tenant_db_a)

    with pytest.raises(KitServiceError) as exc:
        await CourseKitService.add_slide(
            kit.id,
            KitSlideCreate(slide_number=1, title="Blocked Slide"),
            db=tenant_db_a,
        )
    assert exc.value.code == "IMMUTABLE"


async def test_update_slide_changes_title(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    slide = await CourseKitService.add_slide(
        kit.id,
        KitSlideCreate(slide_number=1, title="Original Title"),
        db=tenant_db_a,
    )
    updated = await CourseKitService.update_slide(
        slide.id, kit.id, KitSlideUpdate(title="Updated Title"), db=tenant_db_a
    )
    assert updated.title == "Updated Title"


async def test_delete_slide_removes_it(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    slide = await CourseKitService.add_slide(
        kit.id,
        KitSlideCreate(slide_number=1, title="Slide to Delete"),
        db=tenant_db_a,
    )
    await CourseKitService.delete_slide(slide.id, kit.id, db=tenant_db_a)
    slides = await CourseKitService.list_slides(kit.id, db=tenant_db_a)
    assert all(s.id != slide.id for s in slides)


async def test_reorder_slides_updates_slide_numbers(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    s1 = await CourseKitService.add_slide(
        kit.id, KitSlideCreate(slide_number=1, title="First"), db=tenant_db_a
    )
    s2 = await CourseKitService.add_slide(
        kit.id, KitSlideCreate(slide_number=2, title="Second"), db=tenant_db_a
    )
    # Use non-conflicting target numbers to avoid unique constraint violation
    # from sequential per-row UPDATEs (same as M02's unit reorder pattern).
    count = await CourseKitService.reorder_slides(
        kit.id, {s1.id: 10, s2.id: 20}, db=tenant_db_a
    )
    assert count == 2
    slides = await CourseKitService.list_slides(kit.id, db=tenant_db_a)
    numbers = {s.id: s.slide_number for s in slides}
    assert numbers[s1.id] == 10
    assert numbers[s2.id] == 20


# ===========================================================================
# Assignments
# ===========================================================================

async def test_add_assignment_with_rubric_succeeds(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    assignment = await CourseKitService.add_assignment(
        kit.id,
        KitAssignmentCreate(
            assignment_number=1,
            title="Case Study: Database Design",
            assignment_type=AssignmentType.CASE_STUDY,
            question_text="Design a relational schema for a university management system.",
            model_answer="Identify entities: Student, Course, Faculty, Department...",
            rubric=[
                RubricCriterion(
                    criterion="Schema Design",
                    description="Correctly identifies all entities and relationships",
                    max_marks=10,
                ),
                RubricCriterion(
                    criterion="Normalisation",
                    description="Schema satisfies 3NF requirements",
                    max_marks=5,
                ),
            ],
        ),
        db=tenant_db_a,
    )
    assert assignment.assignment_number == 1
    assert assignment.assignment_type == AssignmentType.CASE_STUDY
    assert len(assignment.rubric) == 2
    assert assignment.model_answer is not None


async def test_update_assignment_updates_rubric(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    assignment = await CourseKitService.add_assignment(
        kit.id,
        KitAssignmentCreate(
            assignment_number=1,
            title="Initial Assignment Title",
            question_text="Initial question text for this assignment here.",
            rubric=[
                RubricCriterion(criterion="C1", description="Original criterion desc", max_marks=5)
            ],
        ),
        db=tenant_db_a,
    )
    from app.modules.m03_course_kit.schemas import KitAssignmentUpdate
    updated = await CourseKitService.update_assignment(
        assignment.id, kit.id,
        KitAssignmentUpdate(
            rubric=[
                RubricCriterion(criterion="C1", description="Updated criterion desc", max_marks=10)
            ]
        ),
        db=tenant_db_a,
    )
    assert updated.rubric[0]["max_marks"] == 10


async def test_delete_assignment_removes_it(tenant_db_a, m02_setup):
    kit = await _create_draft(tenant_db_a, m02_setup["syllabus_id"])
    assignment = await CourseKitService.add_assignment(
        kit.id,
        KitAssignmentCreate(
            assignment_number=1,
            title="Assignment to Delete",
            question_text="This assignment question text will be deleted soon.",
            rubric=[],
        ),
        db=tenant_db_a,
    )
    await CourseKitService.delete_assignment(assignment.id, kit.id, db=tenant_db_a)
    assignments = await CourseKitService.list_assignments(kit.id, db=tenant_db_a)
    assert all(a.id != assignment.id for a in assignments)
