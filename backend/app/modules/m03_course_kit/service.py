"""
M03 CourseKitService — state machine, dispatch, compliance, fork, CRUD.

Architecture contract
---------------------
  - All business logic lives here; routers are pure HTTP glue.
  - KitServiceError carries a machine-readable `code`, human `message`,
    and HTTP `status_code` so routers can raise HTTPException without logic.
  - Generation dispatch: creates a task_jobs row, sets status → AI_GENERATING
    atomically before dispatching so duplicate dispatches are blocked until
    the task finishes.
  - AI advises, humans decide: no grade, penalty, or rejection logic here.
  - Every publish requires an explicit faculty/admin action and passes a
    compliance check; AI generation produces only a DRAFT.
  - One PUBLISHED kit per (syllabus_id, unit_number) — enforced at publish.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m03_course_kit.models import (
    CourseKit,
    CourseKitStatus,
    KitAssignment,
    KitQuizlet,
    KitSlide,
)
from app.modules.m03_course_kit.repository import (
    AssignmentRepository,
    CourseKitRepository,
    QuizletRepository,
    SlideRepository,
    TaskJobPublicRepository,
)
from app.modules.m03_course_kit.schemas import (
    ComplianceCheckResponse,
    ComplianceViolation,
    CourseKitCreate,
    CourseKitUpdate,
    ForkRequest,
    KitAssignmentCreate,
    KitAssignmentUpdate,
    KitQuizletCreate,
    KitQuizletUpdate,
    KitSlideCreate,
    KitSlideUpdate,
)

logger = logging.getLogger("vidya.service.m03")


# ---------------------------------------------------------------------------
# Exported error class
# ---------------------------------------------------------------------------

class KitServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Internal state-guard helpers
# ---------------------------------------------------------------------------

async def _require_kit(kit_id: UUID, *, db: AsyncSession) -> CourseKit:
    kit = await CourseKitRepository.get_by_id(kit_id, db=db)
    if kit is None:
        raise KitServiceError("NOT_FOUND", "Course kit not found.", 404)
    return kit


async def _require_editable(kit_id: UUID, *, db: AsyncSession) -> CourseKit:
    """Raise if status prevents editing (AI_GENERATING, PUBLISHED, ARCHIVED)."""
    kit = await _require_kit(kit_id, db=db)
    if kit.status == CourseKitStatus.DRAFT:
        return kit
    if kit.status == CourseKitStatus.AI_GENERATING:
        raise KitServiceError(
            "GENERATING",
            "AI generation is in progress. Wait for completion before editing.",
            409,
        )
    raise KitServiceError(
        "IMMUTABLE",
        f"Course kit is {kit.status.value} and cannot be edited. "
        "Fork to create a new DRAFT version.",
        409,
    )


# ---------------------------------------------------------------------------
# Compliance helpers (pure functions — no DB access)
# ---------------------------------------------------------------------------

def _build_compliance(
    slide_count: int,
    quizlet_count: int,
    teaching_plan: list,
    min_slides: int,
    min_quizlets: int,
) -> ComplianceCheckResponse:
    violations: list[ComplianceViolation] = []

    if slide_count < min_slides:
        violations.append(ComplianceViolation(
            code="SLIDE_MIN_NOT_MET",
            message=(
                f"At least {min_slides} slides required; "
                f"found {slide_count}."
            ),
            severity="ERROR",
        ))

    if quizlet_count < min_quizlets:
        violations.append(ComplianceViolation(
            code="QUIZLET_MIN_NOT_MET",
            message=(
                f"At least {min_quizlets} quizlets required; "
                f"found {quizlet_count}."
            ),
            severity="ERROR",
        ))

    if not teaching_plan:
        violations.append(ComplianceViolation(
            code="NO_TEACHING_PLAN",
            message=(
                "Teaching plan is empty; recommend generating or adding "
                "a weekly schedule."
            ),
            severity="WARNING",
        ))

    passed = not any(v.severity == "ERROR" for v in violations)
    return ComplianceCheckResponse(passed=passed, violations=violations)


# ---------------------------------------------------------------------------
# CourseKitService
# ---------------------------------------------------------------------------

class CourseKitService:

    # =========================================================================
    # Generation dispatch (added STEP-06, kept here for completeness)
    # =========================================================================

    @staticmethod
    async def dispatch_kit_generation(
        kit_id: UUID,
        tenant_id: UUID,
        schema_name: str,
        *,
        db: AsyncSession,
    ) -> str:
        """
        Queue the AI course-kit generation task.  Returns job_id (str).

        Valid only from DRAFT status.  Sets status to AI_GENERATING atomically
        before dispatching so concurrent re-dispatch requests are rejected until
        the task completes or fails.
        """
        kit = await _require_kit(kit_id, db=db)
        if kit.status != CourseKitStatus.DRAFT:
            raise KitServiceError(
                "INVALID_STATE",
                f"Course kit is {kit.status.value}; "
                "AI generation can only be triggered from DRAFT status.",
                409,
            )

        job_id = await TaskJobPublicRepository.create(
            tenant_id=tenant_id,
            task_type="course_kit_generation",
            queue_name="heavy",
            payload={"kit_id": str(kit_id), "schema_name": schema_name},
            db=db,
        )
        await CourseKitRepository.update_status(
            kit_id, CourseKitStatus.AI_GENERATING, db=db
        )
        await db.commit()

        from app.workers.heavy.course_kit_generation import generate_course_kit  # noqa: PLC0415

        generate_course_kit.delay(
            job_id=str(job_id),
            kit_id=str(kit_id),
            tenant_id=str(tenant_id),
            schema_name=schema_name,
        )
        logger.info(
            "m03.service: AI generation queued (kit=%s job=%s unit=%s)",
            kit_id, job_id, kit.unit_number,
        )
        return str(job_id)

    # =========================================================================
    # Kit CRUD
    # =========================================================================

    @staticmethod
    async def create_kit(
        payload: CourseKitCreate,
        created_by: UUID,
        *,
        db: AsyncSession,
    ) -> CourseKit:
        """
        Create a new DRAFT course kit for a syllabus unit.

        The syllabus must be FACULTY_APPROVED or ADMIN_LOCKED; kits are only
        built on approved syllabi.  Version is auto-incremented per unit.
        """
        from app.modules.m02_syllabus.models import SyllabusStatus
        from app.modules.m02_syllabus.repository import SyllabusRepository

        syllabus = await SyllabusRepository.get_by_id(payload.syllabus_id, db=db)
        if syllabus is None:
            raise KitServiceError("NOT_FOUND", "Syllabus not found.", 404)
        if syllabus.status not in (
            SyllabusStatus.FACULTY_APPROVED,
            SyllabusStatus.ADMIN_LOCKED,
        ):
            raise KitServiceError(
                "SYLLABUS_NOT_APPROVED",
                f"Syllabus is {syllabus.status.value}; "
                "course kits can only be created from an approved or locked syllabus.",
                422,
            )

        complexity = payload.complexity_level or __import__(
            "app.modules.m03_course_kit.models", fromlist=["ComplexityLevel"]
        ).ComplexityLevel.UG

        kit = await CourseKitRepository.create(
            syllabus_id=payload.syllabus_id,
            unit_number=payload.unit_number,
            created_by_user_id=created_by,
            complexity_level=complexity,
            tone=payload.tone,
            custom_instructions=payload.custom_instructions,
            db=db,
        )
        await db.commit()
        return kit

    @staticmethod
    async def get_kit(kit_id: UUID, *, db: AsyncSession) -> CourseKit | None:
        return await CourseKitRepository.get_by_id(kit_id, db=db)

    @staticmethod
    async def get_kit_detail(kit_id: UUID, *, db: AsyncSession) -> CourseKit | None:
        return await CourseKitRepository.get_detail(kit_id, db=db)

    @staticmethod
    async def list_kits(
        syllabus_id: UUID,
        *,
        status_filter: CourseKitStatus | None = None,
        page: int = 1,
        page_size: int = 50,
        db: AsyncSession,
    ) -> tuple[int, list[CourseKit]]:
        offset = (page - 1) * page_size
        total = await CourseKitRepository.count_by_syllabus(
            syllabus_id, status_filter=status_filter, db=db
        )
        items = await CourseKitRepository.list_by_syllabus(
            syllabus_id,
            status_filter=status_filter,
            offset=offset,
            limit=page_size,
            db=db,
        )
        return total, items

    @staticmethod
    async def update_kit(
        kit_id: UUID,
        payload: CourseKitUpdate,
        *,
        db: AsyncSession,
    ) -> CourseKit:
        kit = await _require_editable(kit_id, db=db)
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            return kit
        updates["updated_at"] = datetime.now(timezone.utc)
        updated = await CourseKitRepository.update(kit_id, updates, db=db)
        if updated is None:
            raise KitServiceError("NOT_FOUND", "Course kit not found.", 404)
        await db.commit()
        return updated

    @staticmethod
    async def delete_kit(kit_id: UUID, *, db: AsyncSession) -> None:
        kit = await _require_editable(kit_id, db=db)
        deleted = await CourseKitRepository.delete(kit_id, db=db)
        if not deleted:
            raise KitServiceError("NOT_FOUND", "Course kit not found.", 404)
        await db.commit()

    @staticmethod
    async def list_versions(
        syllabus_id: UUID,
        unit_number: int,
        *,
        db: AsyncSession,
    ) -> list[CourseKit]:
        return await CourseKitRepository.list_versions(
            syllabus_id, unit_number, db=db
        )

    # =========================================================================
    # State transitions
    # =========================================================================

    @staticmethod
    async def publish_kit(
        kit_id: UUID,
        published_by: UUID,
        *,
        db: AsyncSession,
    ) -> CourseKit:
        """
        DRAFT → PUBLISHED.

        Runs compliance checks; blocks on ERROR violations.
        Enforces one-PUBLISHED-per-unit: raises if another kit for this unit
        is already PUBLISHED.
        """
        kit = await _require_kit(kit_id, db=db)
        if kit.status != CourseKitStatus.DRAFT:
            raise KitServiceError(
                "INVALID_STATE",
                f"Only DRAFT kits can be published; kit is {kit.status.value}.",
                409,
            )

        compliance = await CourseKitService.run_compliance_check(kit_id, db=db)
        if not compliance.passed:
            errors = [v.message for v in compliance.violations if v.severity == "ERROR"]
            raise KitServiceError(
                "COMPLIANCE_FAILED",
                f"Kit cannot be published: {'; '.join(errors)}",
                422,
            )

        existing_pub = await CourseKitRepository.get_published_for_unit(
            kit.syllabus_id, kit.unit_number, db=db
        )
        if existing_pub is not None and existing_pub.id != kit_id:
            raise KitServiceError(
                "UNIT_ALREADY_PUBLISHED",
                f"Unit {kit.unit_number} already has a PUBLISHED kit "
                f"(id={existing_pub.id}). "
                "Archive the existing published kit before publishing a new version.",
                409,
            )

        published = await CourseKitRepository.set_published(
            kit_id, published_by, db=db
        )
        if published is None:
            raise KitServiceError("NOT_FOUND", "Course kit not found.", 404)
        await db.commit()
        return published

    @staticmethod
    async def archive_kit(kit_id: UUID, *, db: AsyncSession) -> CourseKit:
        """PUBLISHED → ARCHIVED."""
        kit = await _require_kit(kit_id, db=db)
        if kit.status != CourseKitStatus.PUBLISHED:
            raise KitServiceError(
                "INVALID_STATE",
                f"Only PUBLISHED kits can be archived; kit is {kit.status.value}.",
                409,
            )
        archived = await CourseKitRepository.update_status(
            kit_id, CourseKitStatus.ARCHIVED, db=db
        )
        if archived is None:
            raise KitServiceError("NOT_FOUND", "Course kit not found.", 404)
        await db.commit()
        return archived

    @staticmethod
    async def fork_kit(
        kit_id: UUID,
        forked_by: UUID,
        change_note: str | None,
        *,
        db: AsyncSession,
    ) -> CourseKit:
        """
        Fork any kit state → new DRAFT.

        Deep copy: slides, quizlets (with answer_key), assignments, JSONB
        plan fields.  New kit gets version = max+1, parent_version_id = original.
        """
        original = await CourseKitRepository.get_detail(kit_id, db=db)
        if original is None:
            raise KitServiceError("NOT_FOUND", "Course kit not found.", 404)
        if original.status == CourseKitStatus.AI_GENERATING:
            raise KitServiceError(
                "GENERATING",
                "Cannot fork a kit while AI generation is in progress.",
                409,
            )

        new_version = await CourseKitRepository.get_next_version(
            original.syllabus_id, original.unit_number, db=db
        )

        new_kit = CourseKit(
            syllabus_id=original.syllabus_id,
            unit_number=original.unit_number,
            version=new_version,
            parent_version_id=original.id,
            status=CourseKitStatus.DRAFT,
            complexity_level=original.complexity_level,
            tone=original.tone,
            custom_instructions=original.custom_instructions,
            teaching_plan=list(original.teaching_plan or []),
            lesson_plans=list(original.lesson_plans or []),
            resources=list(original.resources or []),
            ai_model=original.ai_model,
            prompt_hash=original.prompt_hash,
            created_by_user_id=forked_by,
        )
        db.add(new_kit)
        await db.flush()
        await db.refresh(new_kit)

        for s in (original.slides or []):
            db.add(KitSlide(
                kit_id=new_kit.id,
                slide_number=s.slide_number,
                title=s.title,
                content=s.content,
                speaker_notes=s.speaker_notes,
                bloom_level=s.bloom_level,
                co_reference=s.co_reference,
            ))

        for q in (original.quizlets or []):
            db.add(KitQuizlet(
                kit_id=new_kit.id,
                question_number=q.question_number,
                question_text=q.question_text,
                question_type=q.question_type,
                options=q.options,
                answer_key=q.answer_key,
                answer_explanation=q.answer_explanation,
                bloom_level=q.bloom_level,
                co_reference=q.co_reference,
            ))

        for a in (original.assignments or []):
            db.add(KitAssignment(
                kit_id=new_kit.id,
                assignment_number=a.assignment_number,
                title=a.title,
                assignment_type=a.assignment_type,
                question_text=a.question_text,
                complexity_level=a.complexity_level,
                current_events_toggle=a.current_events_toggle,
                model_answer=a.model_answer,
                rubric=a.rubric,
                bloom_level=a.bloom_level,
                co_reference=a.co_reference,
            ))

        await db.flush()
        await db.commit()
        return new_kit

    # =========================================================================
    # Compliance
    # =========================================================================

    @staticmethod
    async def run_compliance_check(
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> ComplianceCheckResponse:
        from app.config import settings

        kit = await _require_kit(kit_id, db=db)
        slide_count   = await SlideRepository.count_by_kit(kit_id, db=db)
        quizlet_count = await QuizletRepository.count_by_kit(kit_id, db=db)

        return _build_compliance(
            slide_count=slide_count,
            quizlet_count=quizlet_count,
            teaching_plan=kit.teaching_plan or [],
            min_slides=settings.M03_MIN_SLIDES_PER_UNIT,
            min_quizlets=settings.M03_MIN_QUIZLETS_PER_UNIT,
        )

    # =========================================================================
    # Job status
    # =========================================================================

    @staticmethod
    async def get_job_status(
        job_id: UUID,
        tenant_id: UUID,
        *,
        db: AsyncSession,
    ) -> dict | None:
        return await TaskJobPublicRepository.get_by_id(
            job_id, tenant_id, db=db
        )

    # =========================================================================
    # Slides
    # =========================================================================

    @staticmethod
    async def list_slides(kit_id: UUID, *, db: AsyncSession) -> list[KitSlide]:
        await _require_kit(kit_id, db=db)
        return await SlideRepository.list_by_kit(kit_id, db=db)

    @staticmethod
    async def add_slide(
        kit_id: UUID,
        payload: KitSlideCreate,
        *,
        db: AsyncSession,
    ) -> KitSlide:
        await _require_editable(kit_id, db=db)
        slide = await SlideRepository.create(
            kit_id=kit_id,
            slide_number=payload.slide_number,
            title=payload.title,
            content=payload.content.model_dump(exclude_none=True),
            speaker_notes=payload.speaker_notes,
            bloom_level=payload.bloom_level,
            co_reference=payload.co_reference,
            db=db,
        )
        await db.commit()
        return slide

    @staticmethod
    async def update_slide(
        slide_id: UUID,
        kit_id: UUID,
        payload: KitSlideUpdate,
        *,
        db: AsyncSession,
    ) -> KitSlide:
        await _require_editable(kit_id, db=db)
        slide = await SlideRepository.get_by_id(slide_id, db=db)
        if slide is None or slide.kit_id != kit_id:
            raise KitServiceError("NOT_FOUND", "Slide not found.", 404)
        updates = payload.model_dump(exclude_none=True)
        if "content" in updates and hasattr(updates["content"], "model_dump"):
            updates["content"] = updates["content"].model_dump(exclude_none=True)
        updates["updated_at"] = datetime.now(timezone.utc)
        updated = await SlideRepository.update(slide_id, updates, db=db)
        if updated is None:
            raise KitServiceError("NOT_FOUND", "Slide not found.", 404)
        await db.commit()
        return updated

    @staticmethod
    async def delete_slide(
        slide_id: UUID,
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        await _require_editable(kit_id, db=db)
        slide = await SlideRepository.get_by_id(slide_id, db=db)
        if slide is None or slide.kit_id != kit_id:
            raise KitServiceError("NOT_FOUND", "Slide not found.", 404)
        await SlideRepository.delete(slide_id, db=db)
        await db.commit()

    @staticmethod
    async def reorder_slides(
        kit_id: UUID,
        order_map: dict[UUID, int],
        *,
        db: AsyncSession,
    ) -> int:
        await _require_editable(kit_id, db=db)
        count = await SlideRepository.reorder(order_map, db=db)
        await db.commit()
        return count

    # =========================================================================
    # Quizlets
    # =========================================================================

    @staticmethod
    async def list_quizlets(kit_id: UUID, *, db: AsyncSession) -> list[KitQuizlet]:
        await _require_kit(kit_id, db=db)
        return await QuizletRepository.list_by_kit(kit_id, db=db)

    @staticmethod
    async def add_quizlet(
        kit_id: UUID,
        payload: KitQuizletCreate,
        *,
        db: AsyncSession,
    ) -> KitQuizlet:
        await _require_editable(kit_id, db=db)
        if not payload.answer_key:
            raise KitServiceError(
                "MISSING_ANSWER_KEY",
                "answer_key is required and must be non-empty.",
                422,
            )
        quizlet = await QuizletRepository.create(
            kit_id=kit_id,
            question_number=payload.question_number,
            question_text=payload.question_text,
            question_type=payload.question_type,
            options=[o.model_dump() for o in payload.options],
            answer_key=payload.answer_key,
            answer_explanation=payload.answer_explanation,
            bloom_level=payload.bloom_level,
            co_reference=payload.co_reference,
            db=db,
        )
        await db.commit()
        return quizlet

    @staticmethod
    async def update_quizlet(
        quizlet_id: UUID,
        kit_id: UUID,
        payload: KitQuizletUpdate,
        *,
        db: AsyncSession,
    ) -> KitQuizlet:
        await _require_editable(kit_id, db=db)
        quizlet = await QuizletRepository.get_by_id(quizlet_id, db=db)
        if quizlet is None or quizlet.kit_id != kit_id:
            raise KitServiceError("NOT_FOUND", "Quizlet not found.", 404)
        updates = payload.model_dump(exclude_none=True)
        if "options" in updates:
            updates["options"] = [
                o.model_dump() if hasattr(o, "model_dump") else o
                for o in updates["options"]
            ]
        updates["updated_at"] = datetime.now(timezone.utc)
        updated = await QuizletRepository.update(quizlet_id, updates, db=db)
        if updated is None:
            raise KitServiceError("NOT_FOUND", "Quizlet not found.", 404)
        await db.commit()
        return updated

    @staticmethod
    async def delete_quizlet(
        quizlet_id: UUID,
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        await _require_editable(kit_id, db=db)
        quizlet = await QuizletRepository.get_by_id(quizlet_id, db=db)
        if quizlet is None or quizlet.kit_id != kit_id:
            raise KitServiceError("NOT_FOUND", "Quizlet not found.", 404)
        await QuizletRepository.delete(quizlet_id, db=db)
        await db.commit()

    # =========================================================================
    # Assignments
    # =========================================================================

    @staticmethod
    async def list_assignments(
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[KitAssignment]:
        await _require_kit(kit_id, db=db)
        return await AssignmentRepository.list_by_kit(kit_id, db=db)

    @staticmethod
    async def add_assignment(
        kit_id: UUID,
        payload: KitAssignmentCreate,
        *,
        db: AsyncSession,
    ) -> KitAssignment:
        await _require_editable(kit_id, db=db)
        assignment = await AssignmentRepository.create(
            kit_id=kit_id,
            assignment_number=payload.assignment_number,
            title=payload.title,
            assignment_type=payload.assignment_type,
            question_text=payload.question_text,
            complexity_level=payload.complexity_level,
            current_events_toggle=payload.current_events_toggle,
            model_answer=payload.model_answer,
            rubric=[r.model_dump() for r in payload.rubric],
            bloom_level=payload.bloom_level,
            co_reference=payload.co_reference,
            db=db,
        )
        await db.commit()
        return assignment

    @staticmethod
    async def update_assignment(
        assignment_id: UUID,
        kit_id: UUID,
        payload: KitAssignmentUpdate,
        *,
        db: AsyncSession,
    ) -> KitAssignment:
        await _require_editable(kit_id, db=db)
        assignment = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if assignment is None or assignment.kit_id != kit_id:
            raise KitServiceError("NOT_FOUND", "Assignment not found.", 404)
        updates = payload.model_dump(exclude_none=True)
        if "rubric" in updates:
            updates["rubric"] = [
                r.model_dump() if hasattr(r, "model_dump") else r
                for r in updates["rubric"]
            ]
        updates["updated_at"] = datetime.now(timezone.utc)
        updated = await AssignmentRepository.update(assignment_id, updates, db=db)
        if updated is None:
            raise KitServiceError("NOT_FOUND", "Assignment not found.", 404)
        await db.commit()
        return updated

    @staticmethod
    async def delete_assignment(
        assignment_id: UUID,
        kit_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        await _require_editable(kit_id, db=db)
        assignment = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if assignment is None or assignment.kit_id != kit_id:
            raise KitServiceError("NOT_FOUND", "Assignment not found.", 404)
        await AssignmentRepository.delete(assignment_id, db=db)
        await db.commit()
