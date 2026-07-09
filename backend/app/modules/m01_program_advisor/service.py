from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m_academics.dean_scope import get_dean_program_ids
from app.modules.m_academics.repository import ProgramRepo as AcadProgramRepo
from app.modules.m01_program_advisor.compliance import (
    ComplianceResult,
    CourseNode,
    ProgramNode,
    run_compliance_check,
)
from app.modules.m01_program_advisor.models import Course, ElectiveBasket, Program, ProgramOutcome, ProgramStatus
from app.modules.m01_program_advisor.repository import (
    CoursePrerequisiteRepository,
    CourseRepository,
    ElectiveBasketRepository,
    ProgramOutcomeRepository,
    ProgramRepository,
    TaskJobPublicRepository,
)
from app.modules.m01_program_advisor.schemas import (
    CourseCreate,
    CourseUpdate,
    ElectiveBasketCreate,
    ElectiveBasketUpdate,
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


async def _require_prepublish_status(
    program_id: UUID,
    *,
    db: AsyncSession,
) -> Program:
    """Accept DRAFT or APPROVED — both remain editable/deletable by the Dean.
    Once PUBLISHED, a program is permanently read-only (no edit, no delete)."""
    _PREPUBLISH = {ProgramStatus.DRAFT, ProgramStatus.APPROVED}
    program = await ProgramRepository.get_by_id(program_id, db=db)
    if program is None:
        raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
    if program.status not in _PREPUBLISH:
        raise ProgramServiceError(
            "INVALID_STATUS",
            f"Program must be Draft or Approved to edit or delete; "
            f"current status is {program.status.value}.",
            409,
        )
    return program


async def _require_deletable_status(
    program_id: UUID,
    *,
    db: AsyncSession,
) -> Program:
    """Accept DRAFT or PENDING_APPROVAL — deletion is allowed while a program
    is still being drafted or is under review, and is progressively locked once
    it is Approved (one step from Published) and permanently once Published.
    Mirrors the Basket/Course deletion window so all three entities share one
    rule: deletable in {DRAFT, PENDING_APPROVAL}, never afterward."""
    _DELETABLE = {ProgramStatus.DRAFT, ProgramStatus.PENDING_APPROVAL}
    program = await ProgramRepository.get_by_id(program_id, db=db)
    if program is None:
        raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
    if program.status not in _DELETABLE:
        raise ProgramServiceError(
            "INVALID_STATUS",
            f"Program must be in Draft or Pending Approval to delete; "
            f"current status is {program.status.value}. "
            f"Create a new version to make changes instead.",
            409,
        )
    return program


async def _require_editable_status(
    program_id: UUID,
    *,
    db: AsyncSession,
) -> Program:
    """Accept DRAFT or PENDING_APPROVAL — both allow structural course edits."""
    _EDITABLE = {ProgramStatus.DRAFT, ProgramStatus.PENDING_APPROVAL}
    program = await ProgramRepository.get_by_id(program_id, db=db)
    if program is None:
        raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
    if program.status not in _EDITABLE:
        raise ProgramServiceError(
            "INVALID_STATUS",
            f"Program must be in Draft or Pending Approval to edit courses; "
            f"current status is {program.status.value}.",
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
            course_type=course.course_type,
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
        if payload.acad_program_id is not None:
            acad_prog = await AcadProgramRepo.get_by_id(payload.acad_program_id, db=db)
            if acad_prog is None or not acad_prog.is_active:
                raise ProgramServiceError(
                    "INVALID_ACAD_PROGRAM",
                    "Academic program not found or is not active.",
                    404,
                )
        program = await ProgramRepository.create(
            title=payload.title,
            degree_type=payload.degree_type,
            department=payload.department,
            duration_years=payload.duration_years,
            total_credits=payload.total_credits,
            created_by_user_id=created_by,
            acad_program_id=payload.acad_program_id,
            ai_instructions=payload.ai_instructions,
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
        caller_role: str | None = None,
        caller_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> Program | None:
        program = await ProgramRepository.get_by_id(program_id, db=db)
        return await ProgramService._apply_dean_visibility(
            program, caller_role=caller_role, caller_user_id=caller_user_id, db=db
        )

    @staticmethod
    async def get_program_detail(
        program_id: UUID,
        *,
        caller_role: str | None = None,
        caller_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> Program | None:
        program = await ProgramRepository.get_detail(program_id, db=db)
        return await ProgramService._apply_dean_visibility(
            program, caller_role=caller_role, caller_user_id=caller_user_id, db=db
        )

    @staticmethod
    async def _apply_dean_visibility(
        program: Program | None,
        *,
        caller_role: str | None,
        caller_user_id: UUID | None,
        db: AsyncSession,
    ) -> Program | None:
        """Hide a program from a DEAN who does not govern it (returns None,
        which routers already translate to a 404 — avoids confirming
        existence of out-of-scope programs to an unauthorized dean)."""
        if program is None or caller_role != "DEAN" or caller_user_id is None:
            return program
        governed = await get_dean_program_ids(caller_user_id, caller_role, db)
        if governed is not None and program.acad_program_id not in governed:
            return None
        return program

    @staticmethod
    async def list_programs(
        status_filter: ProgramStatus | None = None,
        offset: int = 0,
        limit: int = 50,
        *,
        caller_role: str | None = None,
        caller_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> list[Program]:
        acad_program_ids = await ProgramService._resolve_scope(
            caller_role=caller_role, caller_user_id=caller_user_id, db=db
        )
        return await ProgramRepository.list(
            status_filter=status_filter,
            offset=offset,
            limit=limit,
            acad_program_ids=acad_program_ids,
            db=db,
        )

    @staticmethod
    async def count_programs(
        status_filter: ProgramStatus | None = None,
        *,
        caller_role: str | None = None,
        caller_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> int:
        acad_program_ids = await ProgramService._resolve_scope(
            caller_role=caller_role, caller_user_id=caller_user_id, db=db
        )
        return await ProgramRepository.count(
            status_filter=status_filter, acad_program_ids=acad_program_ids, db=db
        )

    @staticmethod
    async def _resolve_scope(
        *,
        caller_role: str | None,
        caller_user_id: UUID | None,
        db: AsyncSession,
    ) -> list[UUID] | None:
        if caller_role != "DEAN" or caller_user_id is None:
            return None
        return await get_dean_program_ids(caller_user_id, caller_role, db)

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
        await _require_prepublish_status(program_id, db=db)
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            raise ProgramServiceError("NO_FIELDS", "No fields to update.", 422)
        if "acad_program_id" in updates:
            acad_prog = await AcadProgramRepo.get_by_id(updates["acad_program_id"], db=db)
            if acad_prog is None or not acad_prog.is_active:
                raise ProgramServiceError(
                    "INVALID_ACAD_PROGRAM",
                    "Academic program not found or is not active.",
                    404,
                )
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
        await _require_deletable_status(program_id, db=db)
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
        ai_instructions: str | None = None,
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

        # Persist ai_instructions update if provided
        if ai_instructions is not None:
            await ProgramRepository.update(
                program_id, {"ai_instructions": ai_instructions}, db=db
            )

        # Merge stored instructions with one-time prompt hint for the worker
        effective_instructions = ai_instructions or program.ai_instructions

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
            ai_instructions=effective_instructions,
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
    async def publish(
        program_id: UUID,
        published_by: UUID,
        *,
        db: AsyncSession,
    ) -> Program:
        """APPROVED -> PUBLISHED. Terminal state: the program becomes
        permanently read-only (see `_require_prepublish_status`), and its
        elective-tagged courses become eligible for Elective Offerings."""
        await _require_status(program_id, ProgramStatus.APPROVED, db=db)
        published = await ProgramRepository.set_published(program_id, published_by, db=db)
        if published is None:
            raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
        await db.commit()
        return published

    @staticmethod
    async def fork_program(
        program_id: UUID,
        created_by: UUID,
        *,
        db: AsyncSession,
    ) -> Program:
        original = await ProgramRepository.get_by_id(program_id, db=db)
        if original is None:
            raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
        if original.status not in (ProgramStatus.APPROVED, ProgramStatus.PUBLISHED):
            raise ProgramServiceError(
                "INVALID_STATUS",
                f"Program must be Approved or Published to duplicate; "
                f"current status is {original.status.value}.",
                409,
            )

        outcomes = await ProgramOutcomeRepository.list_by_program(program_id, db=db)
        original_courses = await CourseRepository.list_by_program(program_id, db=db)
        original_baskets = await ElectiveBasketRepository.list_by_program(program_id, db=db)

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
            acad_program_id=original.acad_program_id,
            ai_instructions=original.ai_instructions,
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

        basket_old_to_new: dict[UUID, UUID] = {}
        for b in original_baskets:
            new_basket = await ElectiveBasketRepository.create(
                new_program.id, b.semester, b.name, b.description, created_by, db=db,
            )
            basket_old_to_new[b.id] = new_basket.id

        if original_courses:
            new_courses = await CourseRepository.bulk_create(
                new_program.id,
                [
                    CourseCreate(
                        code=c.code,
                        title=c.title,
                        credits=c.credits,
                        semester=c.semester,
                        course_type=c.course_type,
                        is_elective=c.is_elective,
                        elective_basket_id=basket_old_to_new.get(c.elective_basket_id) if c.elective_basket_id else None,
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
    async def _validate_basket_assignment(
        program_id: UUID,
        semester: int,
        elective_basket_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> None:
        """A basket may only hold courses from its own program+semester --
        never a free-floating course marked elective with nowhere to live."""
        if elective_basket_id is None:
            return
        basket = await ElectiveBasketRepository.get_by_id(elective_basket_id, db=db)
        if basket is None or basket.program_id != program_id:
            raise ProgramServiceError("BASKET_NOT_FOUND", "Elective basket not found in this program.", 404)
        if basket.semester != semester:
            raise ProgramServiceError(
                "BASKET_SEMESTER_MISMATCH",
                f"This basket belongs to semester {basket.semester}, not {semester}.", 422,
            )

    @staticmethod
    async def add_course(
        program_id: UUID,
        payload: CourseCreate,
        *,
        db: AsyncSession,
    ) -> Course:
        await _require_editable_status(program_id, db=db)
        existing = await CourseRepository.get_by_code(program_id, payload.code, db=db)
        if existing:
            raise ProgramServiceError(
                "CODE_EXISTS", f"Course code {payload.code!r} already exists in this program.", 409
            )
        await ProgramService._validate_basket_assignment(
            program_id, payload.semester, payload.elective_basket_id, db=db,
        )
        # A course inside a basket is an elective by definition.
        is_elective = payload.is_elective or payload.elective_basket_id is not None
        course = await CourseRepository.create(
            program_id=program_id,
            code=payload.code,
            title=payload.title,
            credits=payload.credits,
            semester=payload.semester,
            course_type=payload.course_type.value if payload.course_type else None,
            is_elective=is_elective,
            elective_basket_id=payload.elective_basket_id,
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
        await _require_editable_status(program_id, db=db)
        course = await CourseRepository.get_by_id(course_id, db=db)
        if course is None or course.program_id != program_id:
            raise ProgramServiceError("NOT_FOUND", "Course not found.", 404)
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            raise ProgramServiceError("NO_FIELDS", "No fields to update.", 422)
        if "elective_basket_id" in updates:
            await ProgramService._validate_basket_assignment(
                program_id, updates.get("semester", course.semester), updates["elective_basket_id"], db=db,
            )
            updates["is_elective"] = True
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
        await _require_editable_status(program_id, db=db)
        course = await CourseRepository.get_by_id(course_id, db=db)
        if course is None or course.program_id != program_id:
            raise ProgramServiceError("NOT_FOUND", "Course not found.", 404)
        # DB CASCADE removes course_prerequisites for this course.
        await CourseRepository.delete(course_id, db=db)
        await db.commit()

    # ------------------------------------------------------------------
    # Elective Basket operations (DRAFT/PENDING_APPROVAL guard, same editable
    # window as courses/outcomes — Dean can create any number of electives
    # inside a basket while the Program is still being drafted/reviewed)
    # ------------------------------------------------------------------

    @staticmethod
    async def add_basket(
        program_id: UUID,
        payload: ElectiveBasketCreate,
        created_by: UUID,
        *,
        db: AsyncSession,
    ) -> ElectiveBasket:
        await _require_editable_status(program_id, db=db)
        basket = await ElectiveBasketRepository.create(
            program_id=program_id, semester=payload.semester, name=payload.name,
            description=payload.description, created_by_user_id=created_by, db=db,
        )
        await db.commit()
        return basket

    @staticmethod
    async def update_basket(
        basket_id: UUID,
        program_id: UUID,
        payload: ElectiveBasketUpdate,
        *,
        db: AsyncSession,
    ) -> ElectiveBasket:
        await _require_editable_status(program_id, db=db)
        basket = await ElectiveBasketRepository.get_by_id(basket_id, db=db)
        if basket is None or basket.program_id != program_id:
            raise ProgramServiceError("NOT_FOUND", "Elective basket not found.", 404)
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            raise ProgramServiceError("NO_FIELDS", "No fields to update.", 422)
        updates["updated_at"] = datetime.now(timezone.utc)
        updated = await ElectiveBasketRepository.update(basket_id, updates, db=db)
        await db.commit()
        return updated

    @staticmethod
    async def delete_basket(
        basket_id: UUID,
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        await _require_editable_status(program_id, db=db)
        basket = await ElectiveBasketRepository.get_by_id(basket_id, db=db)
        if basket is None or basket.program_id != program_id:
            raise ProgramServiceError("NOT_FOUND", "Elective basket not found.", 404)
        # DB SET NULL unlinks member courses (they remain, just no longer
        # grouped/offerable as electives until reassigned to another basket).
        await ElectiveBasketRepository.delete(basket_id, db=db)
        await db.commit()

    @staticmethod
    async def list_baskets(program_id: UUID, *, db: AsyncSession) -> list[ElectiveBasket]:
        return await ElectiveBasketRepository.list_by_program(program_id, db=db)

    @staticmethod
    async def remove_course_from_basket(
        course_id: UUID,
        program_id: UUID,
        *,
        db: AsyncSession,
    ) -> Course:
        """Unlink a course from its basket without touching is_elective --
        the Dean may still want it flagged elective while deciding which
        basket (if any) it belongs to next."""
        await _require_editable_status(program_id, db=db)
        course = await CourseRepository.get_by_id(course_id, db=db)
        if course is None or course.program_id != program_id:
            raise ProgramServiceError("NOT_FOUND", "Course not found.", 404)
        updated = await CourseRepository.update(
            course_id, {"elective_basket_id": None, "updated_at": datetime.now(timezone.utc)}, db=db,
        )
        await db.commit()
        return updated

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
        program = await ProgramRepository.get_by_id(program_id, db=db)
        if program is None:
            raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
        if program.status not in (ProgramStatus.APPROVED, ProgramStatus.PUBLISHED):
            raise ProgramServiceError(
                "INVALID_STATUS",
                f"Program must be Approved or Published to export; "
                f"current status is {program.status.value}.",
                409,
            )
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
