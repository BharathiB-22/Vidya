from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m01_program_advisor.compliance import (
    ComplianceResult,
    CourseNode,
    ProgramNode,
    run_compliance_check,
)
from app.modules.m01_program_advisor.models import Course, Program, ProgramOutcome, ProgramStatus
from app.modules.m01_program_advisor.repository import (
    CoursePrerequisiteRepository,
    CourseRepository,
    ProgramOutcomeRepository,
    ProgramRepository,
    TaskJobPublicRepository,
)
from app.modules.m01_program_advisor.schemas import (
    CourseCreate,
    CourseUpdate,
    ProgramCreate,
    ProgramOutcomeCreate,
    ProgramOutcomeUpdate,
    ProgramUpdate,
)


class ProgramServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def _require_status(
    program_id: UUID,
    required: ProgramStatus,
    *,
    db: AsyncSession,
) -> Program:
    program = await ProgramRepository.get_by_id(program_id, db=db)
    if program is None:
        raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
    if program.status != required:
        raise ProgramServiceError(
            "INVALID_STATUS",
            f"Expected status {required.value}, got {program.status.value}.",
            409,
        )
    return program


async def _build_course_nodes(
    program_id: UUID,
    *,
    db: AsyncSession,
) -> list[CourseNode]:
    courses = await CourseRepository.list_by_program(program_id, db=db)
    nodes: list[CourseNode] = []
    for course in courses:
        prereqs = await CoursePrerequisiteRepository.list_by_course(course.id, db=db)
        nodes.append(CourseNode(
            id=course.id,
            code=course.code,
            credits=course.credits,
            semester=course.semester,
            is_elective=course.is_elective,
            prerequisite_course_ids=[p.prerequisite_course_id for p in prereqs],
        ))
    return nodes


class ProgramService:

    # ------------------------------------------------------------------
    # Program CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def create_program(
        payload: ProgramCreate,
        created_by: UUID,
        *,
        db: AsyncSession,
    ) -> Program:
        program = await ProgramRepository.create(
            title=payload.title,
            degree_type=payload.degree_type,
            department=payload.department,
            duration_years=payload.duration_years,
            total_credits=payload.total_credits,
            created_by_user_id=created_by,
            db=db,
        )
        if payload.outcomes:
            await ProgramOutcomeRepository.bulk_create(program.id, payload.outcomes, db=db)
        if payload.courses:
            # Inline CourseCreate may include prerequisite_course_ids referencing UUIDs
            # that do not yet exist; strip them here — wire via add_course after creation.
            bare = [
                CourseCreate(
                    code=c.code,
                    title=c.title,
                    credits=c.credits,
                    semester=c.semester,
                    is_elective=c.is_elective,
                    hours_lecture=c.hours_lecture,
                    hours_tutorial=c.hours_tutorial,
                    hours_practical=c.hours_practical,
                    description=c.description,
                )
                for c in payload.courses
            ]
            await CourseRepository.bulk_create(program.id, bare, db=db)
        await db.commit()
        return program

    @staticmethod
    async def get_program(
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> Program | None:
        return await ProgramRepository.get_by_id(program_id, db=db)

    @staticmethod
    async def get_program_detail(
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> Program | None:
        return await ProgramRepository.get_detail(program_id, db=db)

    @staticmethod
    async def list_programs(
        status_filter: ProgramStatus | None = None,
        offset: int = 0,
        limit: int = 50,
        *,
        db: AsyncSession,
    ) -> list[Program]:
        return await ProgramRepository.list(
            status_filter=status_filter, offset=offset, limit=limit, db=db
        )

    @staticmethod
    async def count_programs(
        status_filter: ProgramStatus | None = None,
        *,
        db: AsyncSession,
    ) -> int:
        return await ProgramRepository.count(status_filter=status_filter, db=db)

    @staticmethod
    async def list_versions(
        parent_version_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[Program]:
        return await ProgramRepository.list_versions(parent_version_id, db=db)

    @staticmethod
    async def update_program(
        program_id: UUID,
        payload: ProgramUpdate,
        *,
        db: AsyncSession,
    ) -> Program:
        await _require_status(program_id, ProgramStatus.DRAFT, db=db)
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            raise ProgramServiceError("NO_FIELDS", "No fields to update.", 422)
        updates["updated_at"] = datetime.now(timezone.utc)
        program = await ProgramRepository.update(program_id, updates, db=db)
        if program is None:
            raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
        await db.commit()
        return program

    @staticmethod
    async def delete_program(
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        await _require_status(program_id, ProgramStatus.DRAFT, db=db)
        # DB-level CASCADE removes outcomes, courses, and course_prerequisites.
        await db.execute(sql_delete(Program).where(Program.id == program_id))
        await db.commit()

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    @staticmethod
    async def dispatch_ai_generation(
        program_id: UUID,
        tenant_id: UUID,
        schema_name: str,
        prompt_hint: str | None,
        *,
        db: AsyncSession,
    ) -> str:
        program = await ProgramRepository.get_by_id(program_id, db=db)
        if program is None:
            raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
        if program.status not in (ProgramStatus.DRAFT, ProgramStatus.GENERATION_FAILED):
            raise ProgramServiceError(
                "INVALID_STATUS",
                f"Expected DRAFT or GENERATION_FAILED, got {program.status.value}.",
                409,
            )

        job_id = await TaskJobPublicRepository.create(
            tenant_id=tenant_id,
            task_type="generate_program_structure",
            queue_name="heavy",
            payload={
                "program_id": str(program_id),
                "schema_name": schema_name,
                "revert": {
                    "table":  "programs",
                    "pk":     str(program_id),
                    "schema": schema_name,
                    "status": ProgramStatus.GENERATION_FAILED.value,
                },
            },
            db=db,
        )
        updated = await ProgramRepository.update_status(
            program_id, ProgramStatus.AI_GENERATING, db=db
        )
        if updated is None:
            raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
        await db.commit()

        # Deferred to avoid circular import at module load time.
        from app.workers.heavy.program_structure import generate_program_structure  # noqa: PLC0415

        generate_program_structure.delay(
            job_id=str(job_id),
            program_id=str(program_id),
            tenant_id=str(tenant_id),
            schema_name=schema_name,
            prompt_hint=prompt_hint,
            _revert_table="programs",
            _revert_pk=str(program_id),
            _revert_schema=schema_name,
            _revert_status=ProgramStatus.GENERATION_FAILED.value,
        )
        return str(job_id)

    @staticmethod
    async def approve(
        program_id: UUID,
        approved_by: UUID,
        *,
        db: AsyncSession,
    ) -> Program:
        program = await _require_status(program_id, ProgramStatus.PENDING_APPROVAL, db=db)

        outcomes = await ProgramOutcomeRepository.list_by_program(program_id, db=db)
        course_nodes = await _build_course_nodes(program_id, db=db)

        program_node = ProgramNode(
            degree_type=program.degree_type,
            duration_years=program.duration_years,
            total_credits=program.total_credits,
            outcome_count=len(outcomes),
        )
        result = run_compliance_check(program_node, course_nodes)
        if not result.passed:
            error_msgs = "; ".join(
                v.message for v in result.violations if v.severity == "ERROR"
            )
            raise ProgramServiceError("COMPLIANCE_FAILED", error_msgs, 422)

        approved = await ProgramRepository.set_approved(program_id, approved_by, db=db)
        if approved is None:
            raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
        await db.commit()
        return approved

    @staticmethod
    async def reject(
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> Program:
        await _require_status(program_id, ProgramStatus.PENDING_APPROVAL, db=db)
        updated = await ProgramRepository.update_status(
            program_id, ProgramStatus.DRAFT, db=db
        )
        if updated is None:
            raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
        await db.commit()
        return updated

    @staticmethod
    async def fork_program(
        program_id: UUID,
        created_by: UUID,
        *,
        db: AsyncSession,
    ) -> Program:
        original = await _require_status(program_id, ProgramStatus.APPROVED, db=db)

        outcomes = await ProgramOutcomeRepository.list_by_program(program_id, db=db)
        original_courses = await CourseRepository.list_by_program(program_id, db=db)

        prereqs_by_course: dict[UUID, list[UUID]] = {}
        for course in original_courses:
            rows = await CoursePrerequisiteRepository.list_by_course(course.id, db=db)
            prereqs_by_course[course.id] = [r.prerequisite_course_id for r in rows]

        new_program = await ProgramRepository.create(
            title=original.title,
            degree_type=original.degree_type,
            department=original.department,
            duration_years=original.duration_years,
            total_credits=original.total_credits,
            created_by_user_id=created_by,
            db=db,
        )
        await ProgramRepository.update(
            new_program.id,
            {
                "parent_version_id": original.id,
                "version": original.version + 1,
                "updated_at": datetime.now(timezone.utc),
            },
            db=db,
        )

        if outcomes:
            await ProgramOutcomeRepository.bulk_create(
                new_program.id,
                [
                    ProgramOutcomeCreate(
                        code=o.code,
                        description=o.description,
                        bloom_level=o.bloom_level,
                        display_order=o.display_order,
                    )
                    for o in outcomes
                ],
                db=db,
            )

        if original_courses:
            new_courses = await CourseRepository.bulk_create(
                new_program.id,
                [
                    CourseCreate(
                        code=c.code,
                        title=c.title,
                        credits=c.credits,
                        semester=c.semester,
                        is_elective=c.is_elective,
                        hours_lecture=c.hours_lecture,
                        hours_tutorial=c.hours_tutorial,
                        hours_practical=c.hours_practical,
                        description=c.description,
                    )
                    for c in original_courses
                ],
                db=db,
            )
            old_to_new: dict[UUID, UUID] = {
                orig.id: new.id
                for orig, new in zip(original_courses, new_courses)
            }
            for orig_course, new_course in zip(original_courses, new_courses):
                remapped = [
                    old_to_new[pid]
                    for pid in prereqs_by_course.get(orig_course.id, [])
                    if pid in old_to_new
                ]
                if remapped:
                    await CoursePrerequisiteRepository.bulk_create(
                        new_course.id, remapped, db=db
                    )

        await db.commit()
        return new_program

    # ------------------------------------------------------------------
    # Outcome operations  (DRAFT guard on every mutating call)
    # ------------------------------------------------------------------

    @staticmethod
    async def add_outcome(
        program_id: UUID,
        payload: ProgramOutcomeCreate,
        *,
        db: AsyncSession,
    ) -> ProgramOutcome:
        await _require_status(program_id, ProgramStatus.DRAFT, db=db)
        existing = await ProgramOutcomeRepository.get_by_code(program_id, payload.code, db=db)
        if existing:
            raise ProgramServiceError(
                "CODE_EXISTS", f"Outcome code {payload.code!r} already exists in this program.", 409
            )
        outcome = await ProgramOutcomeRepository.create(
            program_id=program_id,
            code=payload.code,
            description=payload.description,
            bloom_level=payload.bloom_level,
            display_order=payload.display_order,
            db=db,
        )
        await db.commit()
        return outcome

    @staticmethod
    async def update_outcome(
        outcome_id: UUID,
        program_id: UUID,
        payload: ProgramOutcomeUpdate,
        *,
        db: AsyncSession,
    ) -> ProgramOutcome:
        await _require_status(program_id, ProgramStatus.DRAFT, db=db)
        outcome = await ProgramOutcomeRepository.get_by_id(outcome_id, db=db)
        if outcome is None or outcome.program_id != program_id:
            raise ProgramServiceError("NOT_FOUND", "Outcome not found.", 404)
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            raise ProgramServiceError("NO_FIELDS", "No fields to update.", 422)
        updated = await ProgramOutcomeRepository.update(outcome_id, updates, db=db)
        await db.commit()
        return updated

    @staticmethod
    async def delete_outcome(
        outcome_id: UUID,
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        await _require_status(program_id, ProgramStatus.DRAFT, db=db)
        outcome = await ProgramOutcomeRepository.get_by_id(outcome_id, db=db)
        if outcome is None or outcome.program_id != program_id:
            raise ProgramServiceError("NOT_FOUND", "Outcome not found.", 404)
        await ProgramOutcomeRepository.delete(outcome_id, db=db)
        await db.commit()

    # ------------------------------------------------------------------
    # Course operations  (DRAFT guard on every mutating call)
    # ------------------------------------------------------------------

    @staticmethod
    async def add_course(
        program_id: UUID,
        payload: CourseCreate,
        *,
        db: AsyncSession,
    ) -> Course:
        await _require_status(program_id, ProgramStatus.DRAFT, db=db)
        existing = await CourseRepository.get_by_code(program_id, payload.code, db=db)
        if existing:
            raise ProgramServiceError(
                "CODE_EXISTS", f"Course code {payload.code!r} already exists in this program.", 409
            )
        course = await CourseRepository.create(
            program_id=program_id,
            code=payload.code,
            title=payload.title,
            credits=payload.credits,
            semester=payload.semester,
            is_elective=payload.is_elective,
            hours_lecture=payload.hours_lecture,
            hours_tutorial=payload.hours_tutorial,
            hours_practical=payload.hours_practical,
            description=payload.description,
            db=db,
        )
        if payload.prerequisite_course_ids:
            for prereq_id in payload.prerequisite_course_ids:
                prereq = await CourseRepository.get_by_id(prereq_id, db=db)
                if prereq is None or prereq.program_id != program_id:
                    raise ProgramServiceError(
                        "INVALID_PREREQUISITE",
                        f"Prerequisite course {prereq_id} not found in this program.",
                        422,
                    )
            await CoursePrerequisiteRepository.bulk_create(
                course.id, payload.prerequisite_course_ids, db=db
            )
        await db.commit()
        return course

    @staticmethod
    async def update_course(
        course_id: UUID,
        program_id: UUID,
        payload: CourseUpdate,
        *,
        db: AsyncSession,
    ) -> Course:
        await _require_status(program_id, ProgramStatus.DRAFT, db=db)
        course = await CourseRepository.get_by_id(course_id, db=db)
        if course is None or course.program_id != program_id:
            raise ProgramServiceError("NOT_FOUND", "Course not found.", 404)
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            raise ProgramServiceError("NO_FIELDS", "No fields to update.", 422)
        updates["updated_at"] = datetime.now(timezone.utc)
        updated = await CourseRepository.update(course_id, updates, db=db)
        await db.commit()
        return updated

    @staticmethod
    async def delete_course(
        course_id: UUID,
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        await _require_status(program_id, ProgramStatus.DRAFT, db=db)
        course = await CourseRepository.get_by_id(course_id, db=db)
        if course is None or course.program_id != program_id:
            raise ProgramServiceError("NOT_FOUND", "Course not found.", 404)
        # DB CASCADE removes course_prerequisites for this course.
        await CourseRepository.delete(course_id, db=db)
        await db.commit()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @staticmethod
    async def dispatch_export(
        program_id: UUID,
        export_format: str,
        *,
        tenant_id: UUID,
        schema_name: str,
        requested_by_user_id: UUID,
        db: AsyncSession,
    ) -> UUID:
        await _require_status(program_id, ProgramStatus.APPROVED, db=db)
        job_id = await TaskJobPublicRepository.create(
            tenant_id=tenant_id,
            task_type="export_program",
            queue_name="heavy",
            payload={"program_id": str(program_id), "format": export_format},
            db=db,
        )
        await db.commit()

        # Deferred to avoid circular import at module load time.
        from app.workers.heavy.program_export import export_program  # noqa: PLC0415

        export_program.delay(
            job_id=str(job_id),
            program_id=str(program_id),
            tenant_id=str(tenant_id),
            schema_name=schema_name,
            export_format=export_format,
            requested_by_user_id=str(requested_by_user_id),
        )
        return job_id

    # ------------------------------------------------------------------
    # Jobs and compliance  (read-only — no commit)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_job_status(
        job_id: UUID,
        tenant_id: UUID,
        *,
        db: AsyncSession,
    ) -> dict | None:
        return await TaskJobPublicRepository.get_by_id(job_id, tenant_id, db=db)

    @staticmethod
    async def run_compliance(
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> ComplianceResult:
        program = await ProgramRepository.get_by_id(program_id, db=db)
        if program is None:
            raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
        outcomes = await ProgramOutcomeRepository.list_by_program(program_id, db=db)
        course_nodes = await _build_course_nodes(program_id, db=db)
        program_node = ProgramNode(
            degree_type=program.degree_type,
            duration_years=program.duration_years,
            total_credits=program.total_credits,
            outcome_count=len(outcomes),
        )
        return run_compliance_check(program_node, course_nodes)
