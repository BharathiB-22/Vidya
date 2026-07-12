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
    KitSlide,
)
from app.modules.m03_course_kit.repository import (
    AssignmentRepository,
    CourseKitRepository,
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
    KitResourceConfirmRequest,
    KitResourceUploadUrlRequest,
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

async def _assert_faculty_assigned(
    kit: CourseKit,
    faculty_user_id: UUID,
    *,
    db: AsyncSession,
) -> None:
    """Raise 403 unless faculty_user_id has an active teaching assignment for
    the course backing this kit's syllabus.

    Faculty must only see/edit course kits for courses assigned to them —
    never another faculty member's kit for a course they don't teach.
    """
    from app.modules.m02_syllabus.repository import SyllabusRepository
    from app.modules.m_academics.assignment_repository import SubjectAssignmentRepository

    syllabus = await SyllabusRepository.get_by_id(kit.syllabus_id, db=db)
    if syllabus is None:
        raise KitServiceError("NOT_FOUND", "Course kit not found.", 404)
    assignment = await SubjectAssignmentRepository.get_active_for_faculty_course(
        syllabus.course_id, faculty_user_id, db=db
    )
    if assignment is None:
        raise KitServiceError(
            "NOT_ASSIGNED",
            "You are not assigned to teach this course.",
            403,
        )


async def _assert_dean_governs_kit(
    kit: "CourseKit", dean_user_id: UUID, *, db: AsyncSession
) -> None:
    from app.modules.m01_program_advisor.models import Course, Program
    from app.modules.m02_syllabus.repository import SyllabusRepository
    from app.modules.m_academics.dean_scope import get_dean_program_ids
    from sqlalchemy import select

    governed = await get_dean_program_ids(dean_user_id, "DEAN", db)
    if governed is None:
        return
    syllabus = await SyllabusRepository.get_by_id(kit.syllabus_id, db=db)
    if syllabus is None:
        raise KitServiceError("NOT_FOUND", "Course kit not found.", 404)
    result = await db.execute(
        select(Program.acad_program_id)
        .join(Course, Course.program_id == Program.id)
        .where(Course.id == syllabus.course_id)
    )
    acad_program_id = result.scalar_one_or_none()
    if acad_program_id is None or acad_program_id not in governed:
        raise KitServiceError(
            "NOT_IN_SCOPE",
            "You may only manage course kits for programs you govern.",
            403,
        )


async def _require_kit(
    kit_id: UUID,
    *,
    db: AsyncSession,
    caller_role: str | None = None,
    faculty_user_id: UUID | None = None,
) -> CourseKit:
    kit = await CourseKitRepository.get_by_id(kit_id, db=db)
    if kit is None:
        raise KitServiceError("NOT_FOUND", "Course kit not found.", 404)
    if caller_role == "FACULTY" and faculty_user_id is not None:
        await _assert_faculty_assigned(kit, faculty_user_id, db=db)
    if caller_role == "DEAN" and faculty_user_id is not None:
        await _assert_dean_governs_kit(kit, faculty_user_id, db=db)
    return kit


async def _require_editable(
    kit_id: UUID,
    *,
    db: AsyncSession,
    caller_role: str | None = None,
    faculty_user_id: UUID | None = None,
) -> CourseKit:
    """Raise if status prevents editing (AI_GENERATING, PUBLISHED, ARCHIVED)."""
    kit = await _require_kit(
        kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
    )
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
    teaching_plan: list,
    min_slides: int,
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
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> str:
        """
        Queue the AI course-kit generation task.  Returns job_id (str).

        Valid only from DRAFT status.  Sets status to AI_GENERATING atomically
        before dispatching so concurrent re-dispatch requests are rejected until
        the task completes or fails.
        """
        kit = await _require_kit(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
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

        The syllabus must be APPROVED or LOCKED; kits are only
        built on dean-approved syllabi.  Version is auto-incremented per unit.
        """
        from app.modules.m02_syllabus.models import SyllabusStatus
        from app.modules.m02_syllabus.repository import SyllabusRepository
        from app.modules.m01_program_advisor.compliance import classify_degree_level
        from app.modules.m01_program_advisor.repository import (
            CourseRepository,
            ProgramRepository,
        )
        from app.modules.m03_course_kit.models import ComplexityLevel

        syllabus = await SyllabusRepository.get_by_id(payload.syllabus_id, db=db)
        if syllabus is None:
            raise KitServiceError("NOT_FOUND", "Syllabus not found.", 404)
        if syllabus.status not in (
            SyllabusStatus.APPROVED,
            SyllabusStatus.LOCKED,
        ):
            raise KitServiceError(
                "SYLLABUS_NOT_APPROVED",
                f"Syllabus is {syllabus.status.value}; "
                "course kits require a Dean-approved or locked syllabus.",
                422,
            )

        # Default complexity_level from the program's actual degree type
        # (Program.degree_type -> UG/PG) instead of hardcoding UG, so a
        # course kit for an MCA/M.Tech course correctly defaults to PG.
        # An explicit payload.complexity_level always wins.
        default_complexity = ComplexityLevel.UG
        course = await CourseRepository.get_by_id(syllabus.course_id, db=db)
        if course is not None:
            program = await ProgramRepository.get_by_id(course.program_id, db=db)
            if program is not None and classify_degree_level(program.degree_type) == "PG":
                default_complexity = ComplexityLevel.PG
        complexity = payload.complexity_level or default_complexity

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
    async def get_kit(
        kit_id: UUID,
        *,
        db: AsyncSession,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
    ) -> CourseKit | None:
        kit = await CourseKitRepository.get_by_id(kit_id, db=db)
        if kit is not None and caller_role == "FACULTY" and faculty_user_id is not None:
            await _assert_faculty_assigned(kit, faculty_user_id, db=db)
        if kit is not None and caller_role == "DEAN" and faculty_user_id is not None:
            await _assert_dean_governs_kit(kit, faculty_user_id, db=db)
        return kit

    @staticmethod
    async def get_kit_detail(
        kit_id: UUID,
        *,
        db: AsyncSession,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
    ) -> CourseKit | None:
        kit = await CourseKitRepository.get_detail(kit_id, db=db)
        if kit is not None and caller_role == "FACULTY" and faculty_user_id is not None:
            await _assert_faculty_assigned(kit, faculty_user_id, db=db)
        if kit is not None and caller_role == "DEAN" and faculty_user_id is not None:
            await _assert_dean_governs_kit(kit, faculty_user_id, db=db)
        return kit

    @staticmethod
    async def list_kits(
        syllabus_id: UUID | None,
        *,
        status_filter: CourseKitStatus | None = None,
        page: int = 1,
        page_size: int = 50,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> tuple[int, list[CourseKit]]:
        offset = (page - 1) * page_size

        if caller_role == "DEAN" and faculty_user_id is not None:
            from app.modules.m02_syllabus.models import Syllabus
            from app.modules.m01_program_advisor.models import Course, Program
            from app.modules.m_academics.dean_scope import get_dean_program_ids
            from sqlalchemy import select

            governed = await get_dean_program_ids(faculty_user_id, "DEAN", db)
            if governed is not None:
                course_subq = (
                    select(Course.id)
                    .join(Program, Program.id == Course.program_id)
                    .where(Program.acad_program_id.in_(governed))
                )
                governed_syllabus_ids = set(
                    (
                        await db.execute(
                            select(Syllabus.id).where(Syllabus.course_id.in_(course_subq))
                        )
                    ).scalars().all()
                )
                if syllabus_id is not None:
                    if syllabus_id not in governed_syllabus_ids:
                        raise KitServiceError(
                            "NOT_IN_SCOPE",
                            "You may only view course kits for programs you govern.",
                            403,
                        )
                else:
                    syllabus_ids = list(governed_syllabus_ids)
                    total = await CourseKitRepository.count_by_syllabus_ids(
                        syllabus_ids, status_filter=status_filter, db=db
                    )
                    items = await CourseKitRepository.list_by_syllabus_ids(
                        syllabus_ids, status_filter=status_filter,
                        offset=offset, limit=page_size, db=db,
                    )
                    return total, items

        if caller_role == "FACULTY" and faculty_user_id is not None:
            from app.modules.m02_syllabus.models import Syllabus
            from app.modules.m_academics.assignment_repository import SubjectAssignmentRepository
            from sqlalchemy import select

            if syllabus_id is not None:
                syllabus = await db.get(Syllabus, syllabus_id)
                if syllabus is None:
                    raise KitServiceError("NOT_FOUND", "Syllabus not found.", 404)
                assignment = await SubjectAssignmentRepository.get_active_for_faculty_course(
                    syllabus.course_id, faculty_user_id, db=db
                )
                if assignment is None:
                    raise KitServiceError(
                        "NOT_ASSIGNED", "You are not assigned to this course.", 403,
                    )
            else:
                # No syllabus filter: scope to syllabi of assigned courses only.
                assignments = await SubjectAssignmentRepository.list_by_faculty(
                    faculty_user_id, db=db
                )
                course_ids = list({a.course_id for a in assignments})
                syllabus_ids: list[UUID] = []
                if course_ids:
                    result = await db.execute(
                        select(Syllabus.id).where(Syllabus.course_id.in_(course_ids))
                    )
                    syllabus_ids = [row[0] for row in result.all()]
                total = await CourseKitRepository.count_by_syllabus_ids(
                    syllabus_ids, status_filter=status_filter, db=db
                )
                items = await CourseKitRepository.list_by_syllabus_ids(
                    syllabus_ids, status_filter=status_filter,
                    offset=offset, limit=page_size, db=db,
                )
                return total, items

        if syllabus_id is not None:
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
        else:
            total = await CourseKitRepository.count_all(status_filter=status_filter, db=db)
            items = await CourseKitRepository.list_all(
                status_filter=status_filter, offset=offset, limit=page_size, db=db
            )
        return total, items

    @staticmethod
    async def update_kit(
        kit_id: UUID,
        payload: CourseKitUpdate,
        *,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> CourseKit:
        kit = await _require_editable(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
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
    async def delete_kit(
        kit_id: UUID,
        *,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> None:
        kit = await _require_editable(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
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
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> CourseKit:
        """
        DRAFT → PUBLISHED.

        Runs compliance checks; blocks on ERROR violations.
        Enforces one-PUBLISHED-per-unit: raises if another kit for this unit
        is already PUBLISHED.
        """
        kit = await _require_kit(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
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
    async def archive_kit(
        kit_id: UUID,
        *,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> CourseKit:
        """PUBLISHED → ARCHIVED."""
        kit = await _require_kit(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
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
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> CourseKit:
        """
        Fork any kit state → new DRAFT.

        Deep copy: slides, assignments, JSONB plan fields.
        New kit gets version = max+1, parent_version_id = original.
        """
        original = await CourseKitRepository.get_detail(kit_id, db=db)
        if original is None:
            raise KitServiceError("NOT_FOUND", "Course kit not found.", 404)
        if caller_role == "FACULTY" and faculty_user_id is not None:
            await _assert_faculty_assigned(original, faculty_user_id, db=db)
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
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> ComplianceCheckResponse:
        from app.config import settings

        kit = await _require_kit(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
        slide_count = await SlideRepository.count_by_kit(kit_id, db=db)

        return _build_compliance(
            slide_count=slide_count,
            teaching_plan=kit.teaching_plan or [],
            min_slides=settings.M03_MIN_SLIDES_PER_UNIT,
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
    # Export
    # =========================================================================

    @staticmethod
    async def dispatch_kit_export(
        kit_id: UUID,
        export_format: str,
        requested_by: UUID,
        requested_by_role: str,
        tenant_id: UUID,
        schema_name: str,
        *,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> str:
        """
        Queue the export task.  Returns job_id (str).

        Kit must be PUBLISHED or ARCHIVED.  Format must be 'pdf', 'pptx', or 'handout'.
        'handout' always produces a sanitized student PDF (no speaker_notes / answer_key /
        model_answer / rubric) regardless of role.
        requested_by_role is forwarded to the task for DEAN sensitive-field
        gating on 'pdf' and 'pptx' exports.
        """
        from app.workers.heavy.course_kit_export import export_course_kit  # noqa: PLC0415

        kit = await _require_kit(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
        if kit.status not in (CourseKitStatus.PUBLISHED, CourseKitStatus.ARCHIVED):
            raise KitServiceError(
                "INVALID_STATE",
                f"Export requires PUBLISHED or ARCHIVED kit; kit is {kit.status.value}.",
                422,
            )
        if export_format not in ("pdf", "pptx", "handout"):
            raise KitServiceError(
                "INVALID_FORMAT",
                "Export format must be 'pdf', 'pptx', or 'handout'.",
                422,
            )

        job_id = await TaskJobPublicRepository.create(
            tenant_id=tenant_id,
            task_type="course_kit_export",
            queue_name="heavy",
            payload={
                "kit_id":        str(kit_id),
                "format":        export_format,
                "schema_name":   schema_name,
            },
            db=db,
        )
        await db.commit()

        export_course_kit.delay(
            job_id=str(job_id),
            kit_id=str(kit_id),
            tenant_id=str(tenant_id),
            schema_name=schema_name,
            export_format=export_format,
            requested_by_user_id=str(requested_by),
            requested_by_role=requested_by_role,
        )
        logger.info(
            "m03.service: export queued (kit=%s format=%s job=%s)",
            kit_id, export_format, job_id,
        )
        return str(job_id)

    @staticmethod
    async def list_exports(
        kit_id: UUID,
        *,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> list:
        """Return storage assets for this kit (most-recent-first)."""
        from app.core.storage.models import StorageEntityType
        from app.core.storage.repository import StorageRepository

        await _require_kit(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
        return await StorageRepository.list_by_entity(
            StorageEntityType.COURSE_KIT_EXPORT.value,
            kit_id,
            db=db,
        )

    @staticmethod
    async def get_export_download(
        kit_id: UUID,
        asset_id: UUID,
        *,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> tuple:
        """Return (StorageAsset, presigned_download_url) for an export asset."""
        from app.core.storage.repository import StorageRepository

        await _require_kit(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
        asset = await StorageRepository.get_by_id(asset_id, db=db)
        if asset is None or asset.entity_id != kit_id:
            raise KitServiceError("NOT_FOUND", "Export asset not found.", 404)

        url = await StorageRepository.generate_presigned_get_url(
            object_key=asset.object_key,
            expires_in_seconds=86_400,
        )
        return asset, url

    # =========================================================================
    # Slides
    # =========================================================================

    @staticmethod
    async def list_slides(
        kit_id: UUID,
        *,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> list[KitSlide]:
        await _require_kit(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
        return await SlideRepository.list_by_kit(kit_id, db=db)

    @staticmethod
    async def add_slide(
        kit_id: UUID,
        payload: KitSlideCreate,
        *,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> KitSlide:
        await _require_editable(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
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
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> KitSlide:
        await _require_editable(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
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
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> None:
        await _require_editable(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
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
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> int:
        await _require_editable(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
        count = await SlideRepository.reorder(order_map, db=db)
        await db.commit()
        return count

    # =========================================================================
    # Assignments
    # =========================================================================

    @staticmethod
    async def list_assignments(
        kit_id: UUID,
        *,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> list[KitAssignment]:
        await _require_kit(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
        return await AssignmentRepository.list_by_kit(kit_id, db=db)

    @staticmethod
    async def add_assignment(
        kit_id: UUID,
        payload: KitAssignmentCreate,
        *,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> KitAssignment:
        kit = await _require_editable(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
        assignment = await AssignmentRepository.create(
            kit_id=kit_id,
            assignment_number=payload.assignment_number,
            title=payload.title,
            assignment_type=payload.assignment_type,
            question_text=payload.question_text,
            complexity_level=payload.complexity_level or kit.complexity_level,
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
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> KitAssignment:
        await _require_editable(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
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
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> None:
        await _require_editable(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
        assignment = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if assignment is None or assignment.kit_id != kit_id:
            raise KitServiceError("NOT_FOUND", "Assignment not found.", 404)
        await AssignmentRepository.delete(assignment_id, db=db)
        await db.commit()

    # =========================================================================
    # Faculty-uploaded resources (PDF/PPT/DOCX/notes)
    #
    # Reuses the generic storage module (StorageService/StorageRepository,
    # backend/app/core/storage/) — no new table, no new S3 code. This layer
    # only adds Course-Kit-specific authorization: the router's FACULTY/ADMIN
    # (_WRITE) / ADMIN+DEAN+FACULTY (_READ) gates, plus verifying the asset
    # actually belongs to this kit before allowing download/delete. Any kit
    # status may receive resources — they are supplementary material, not
    # part of the generated/compliance-gated kit content.
    # =========================================================================

    @staticmethod
    async def generate_resource_upload_url(
        kit_id: UUID,
        payload: KitResourceUploadUrlRequest,
        *,
        tenant_slug: str,
        current_user_id: UUID,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ):
        from app.core.storage.models import StorageEntityType
        from app.core.storage.schemas import GenerateUploadUrlRequest
        from app.core.storage.service import StorageError, StorageService

        await _require_kit(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
        try:
            return await StorageService.generate_upload_url(
                GenerateUploadUrlRequest(
                    entity_type=StorageEntityType.COURSE_KIT.value,
                    entity_id=kit_id,
                    original_filename=payload.original_filename,
                    content_type=payload.content_type,
                    size_bytes=payload.size_bytes,
                ),
                tenant_slug=tenant_slug,
                current_user_id=current_user_id,
                db=db,
            )
        except StorageError as e:
            raise KitServiceError(e.code, e.message, e.status_code)

    @staticmethod
    async def add_resource(
        kit_id: UUID,
        payload: KitResourceConfirmRequest,
        *,
        tenant_id: UUID,
        tenant_slug: str,
        current_user_id: UUID,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ):
        from app.core.storage.models import StorageEntityType
        from app.core.storage.service import StorageError, StorageService

        await _require_kit(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
        try:
            return await StorageService.create_asset(
                object_key=payload.object_key,
                uploaded_by_user_id=current_user_id,
                entity_type=StorageEntityType.COURSE_KIT.value,
                entity_id=kit_id,
                original_filename=payload.original_filename,
                size_bytes=payload.size_bytes,
                content_type=payload.content_type,
                tenant_id=tenant_id,
                tenant_slug=tenant_slug,
                db=db,
            )
        except StorageError as e:
            raise KitServiceError(e.code, e.message, e.status_code)

    @staticmethod
    async def list_resources(
        kit_id: UUID,
        *,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ):
        from app.core.storage.models import StorageEntityType
        from app.core.storage.repository import StorageRepository
        from app.core.storage.schemas import StorageAssetResponse

        await _require_kit(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
        rows = await StorageRepository.list_by_entity(
            entity_type=StorageEntityType.COURSE_KIT.value,
            entity_id=kit_id,
            limit=200,
            db=db,
        )
        return [StorageAssetResponse.model_validate(r) for r in rows]

    @staticmethod
    async def _require_kit_resource(
        kit_id: UUID,
        asset_id: UUID,
        *,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ):
        from app.core.storage.models import StorageEntityType
        from app.core.storage.repository import StorageRepository

        await _require_kit(
            kit_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
        asset = await StorageRepository.get_by_id(asset_id, db=db)
        if (
            asset is None
            or asset.entity_type != StorageEntityType.COURSE_KIT.value
            or asset.entity_id != kit_id
        ):
            raise KitServiceError("NOT_FOUND", "Resource not found on this kit.", 404)
        return asset

    @staticmethod
    async def get_resource_download_url(
        kit_id: UUID,
        asset_id: UUID,
        *,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> str:
        from app.config import settings
        from app.core.storage.repository import StorageRepository

        asset = await CourseKitService._require_kit_resource(
            kit_id, asset_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
        expires_in_sec = settings.PRESIGNED_URL_EXPIRY_MINUTES_GET * 60
        return await StorageRepository.generate_presigned_get_url(
            object_key=asset.object_key,
            expires_in_seconds=expires_in_sec,
        )

    @staticmethod
    async def delete_resource(
        kit_id: UUID,
        asset_id: UUID,
        *,
        caller_role: str | None = None,
        faculty_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> None:
        from app.core.storage.repository import StorageRepository

        await CourseKitService._require_kit_resource(
            kit_id, asset_id, db=db, caller_role=caller_role, faculty_user_id=faculty_user_id
        )
        await StorageRepository.delete(asset_id, db=db)
        await db.commit()
