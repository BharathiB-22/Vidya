from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("vidya.service.m01")

from app.modules.m_academics.dean_scope import get_dean_program_ids
from app.modules.m_academics.repository import ProgramRepo as AcadProgramRepo
from app.modules.m01_program_advisor.compliance import (
    ComplianceResult,
    CourseNode,
    ElectiveSlotNode,
    ProgramNode,
    run_compliance_check,
)
from app.modules.m01_program_advisor.course_codes import generate_course_code
from app.modules.m01_program_advisor.electives import (
    is_basket_placeholder,
    placeholder_message,
)
from app.modules.m01_program_advisor.models import (
    Course,
    ElectiveBasket,
    ElectiveSlotStatus,
    Program,
    ProgramOutcome,
    ProgramStatus,
)
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
    ElectiveChoiceCreate,
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


# ---------------------------------------------------------------------------
# Edit windows (Phase A — Academic Governance)
#
# A curriculum is editable in exactly two windows, and WHO may edit depends on
# which window it is in:
#
#   DRAFT / GENERATION_FAILED   the DEAN owns it and edits freely
#   PENDING_APPROVAL            the BOARD owns it and edits freely, for the WHOLE
#                               of the window — right up to approval. The Dean is
#                               read-only, permanently: submitting is a one-way
#                               handover with no path back.
#   APPROVED / PUBLISHED        LOCKED — nobody edits, ever. A change means a new
#                               curriculum version.
#
# The status half of that rule lives here. The role half lives in the router's
# `assert_can_edit_structure` dependency, which is the only thing that knows who
# the caller is.
# ---------------------------------------------------------------------------

DEAN_EDIT_STATUSES = {
    ProgramStatus.DRAFT,
    ProgramStatus.GENERATION_FAILED,
}
GOVERNANCE_EDIT_STATUSES = {ProgramStatus.PENDING_APPROVAL}
EDITABLE_STATUSES = DEAN_EDIT_STATUSES | GOVERNANCE_EDIT_STATUSES

# Course fields the official syllabus is built on. Editing any of them
# un-approves that course's syllabus (see update_course).
#
#   code, title      print in the syllabus header
#   credits          prints in the header
#   hours_*          are the L-T-P, from which contact hours are derived, against
#                    which the unit hours are paced
#   semester         places the subject in the curriculum
#   course_type      decides whether a Practical Components section belongs
#
# `description` is deliberately absent: it is prose about the course, and does
# not change what the syllabus teaches.
_SYLLABUS_BEARING_FIELDS = {
    "code", "title", "credits", "semester", "course_type",
    "hours_lecture", "hours_tutorial", "hours_practical",
}


async def _require_editable_status(
    program_id: UUID,
    *,
    db: AsyncSession,
) -> Program:
    """The curriculum is in an editable window at all (role check is separate)."""
    program = await ProgramRepository.get_by_id(program_id, db=db)
    if program is None:
        raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
    if program.status not in EDITABLE_STATUSES:
        raise ProgramServiceError(
            "CURRICULUM_LOCKED",
            f"This curriculum is {program.status.value} and can no longer be edited. "
            f"Create a new version to make changes.",
            409,
        )
    return program


# Program metadata edits follow the same window as structural edits.
_require_prepublish_status = _require_editable_status


async def _require_deletable_status(
    program_id: UUID,
    *,
    db: AsyncSession,
) -> Program:
    """Deletable only while the Dean still holds it: DRAFT.

    Once submitted, the curriculum is in front of the Board and cannot be pulled
    out from under them; once approved it is locked for good.
    """
    _DELETABLE = {ProgramStatus.DRAFT, ProgramStatus.GENERATION_FAILED}
    program = await ProgramRepository.get_by_id(program_id, db=db)
    if program is None:
        raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
    if program.status not in _DELETABLE:
        raise ProgramServiceError(
            "INVALID_STATUS",
            f"Only a Draft curriculum can be deleted; "
            f"current status is {program.status.value}. "
            f"Create a new version to make changes instead.",
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
            elective_basket_id=course.elective_basket_id,
            prerequisite_course_ids=[p.prerequisite_course_id for p in prereqs],
        ))
    return nodes


async def _build_elective_slot_nodes(
    program_id: UUID,
    *,
    db: AsyncSession,
) -> list[ElectiveSlotNode]:
    baskets = await ElectiveBasketRepository.list_by_program(program_id, db=db)
    return [
        ElectiveSlotNode(
            id=basket.id,
            name=basket.name,
            credits=basket.credits,
            semester=basket.semester,
        )
        for basket in baskets
    ]


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
            regulation_year=payload.regulation_year,
            effective_from_batch_id=payload.effective_from_batch_id,
            db=db,
        )
        if payload.outcomes:
            await ProgramOutcomeRepository.bulk_create(program.id, payload.outcomes, db=db)
        if payload.courses:
            # Inline CourseCreate may include prerequisite_course_ids referencing UUIDs
            # that do not yet exist; strip them here — wire via add_course after creation.
            #
            # Everything else is carried over verbatim, course_type included: it was
            # omitted here, so a program created with its courses inline (an import, a
            # seeded programme, a client that posts the whole structure at once) lost
            # the type of every one of them and got a five-unit theory syllabus for its
            # internship. add_course, the AI worker and duplicate_program all preserve
            # it; this path was the odd one out.
            bare = [
                CourseCreate(
                    code=c.code,
                    title=c.title,
                    credits=c.credits,
                    semester=c.semester,
                    course_type=c.course_type,
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

    # NOTE (Phase A): approve / return-to-Dean are NOT here. Approving and
    # locking a curriculum is the governance authority's act, not the Dean's,
    # and it lives in app.core.governance.service alongside the approval-request
    # ledger and the separation-of-duties checks. The Dean's two acts on the
    # approval path are `submit` (also in core.governance) and `publish` below.

    @staticmethod
    async def publish(
        program_id: UUID,
        published_by: UUID,
        *,
        db: AsyncSession,
    ) -> Program:
        """APPROVED -> PUBLISHED. The Dean releases the curriculum.

        TWO STAGES, TWO AUTHORITIES, AND THE SECOND ONE IS THIS.

        The Board approves the TAUGHT curriculum — theory, laboratories, every elective
        option — and the curriculum becomes APPROVED. That publishes nothing. What the
        Board has said is "this is what we teach", and it is frozen.

        The Dean then prepares what the Board does not own: the internship, the mini and
        major projects, the seminar. Each has its own life — drafted, reviewed, approved
        by him. Only when the Board's half is approved AND every one of his own documents
        is approved may he publish. Publishing a curriculum whose internship nobody has
        written yet would release to students a programme with a component that does not
        exist, and they would find out in their final year.

        PUBLISHING CHANGES NO CONTENT. It never regenerates, never edits, never rewrites.
        It moves a state and freezes the Dean's documents so that what students were shown
        stays what students were shown — the taught syllabi were already frozen at
        approval. Everything published is immutable; a change after this is a new version,
        never an edit to the record.
        """
        await _require_status(program_id, ProgramStatus.APPROVED, db=db)

        # THE PUBLISH GATE — every execution document approved by the Dean.
        unready = await ProgramService._unready_execution_documents(program_id, db=db)
        if unready:
            listed = "; ".join(unready[:8])
            if len(unready) > 8:
                listed += f"; and {len(unready) - 8} more"
            raise ProgramServiceError(
                "EXECUTION_DOCUMENTS_INCOMPLETE",
                "This curriculum cannot be published yet. Every internship, project and "
                "seminar needs its document prepared and approved first — a published "
                "curriculum promises students a programme, and a component nobody has "
                f"written is a promise it cannot keep. Outstanding: {listed}",
                422,
            )

        # Freeze the Dean's documents at publication. The Board's were frozen at
        # approval; these are frozen now, because now is when they become the thing a
        # student is assessed against. After this, a change is a new version — never an
        # edit to a published record.
        await db.execute(
            sa_text(
                "UPDATE syllabi SET status = 'LOCKED', locked_by_user_id = :u, "
                "locked_at = now(), updated_at = now() "
                "WHERE course_id IN (SELECT id FROM courses WHERE program_id = :p) "
                "AND status = 'APPROVED' "
                "AND doc_type IN ('INTERNSHIP', 'MINI_PROJECT', 'MAJOR_PROJECT', 'SEMINAR')"
            ),
            {"u": str(published_by), "p": str(program_id)},
        )

        published = await ProgramRepository.set_published(program_id, published_by, db=db)
        if published is None:
            raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)
        await db.commit()
        return published

    @staticmethod
    async def _unready_execution_documents(
        program_id: UUID, *, db: AsyncSession,
    ) -> list[str]:
        """The Dean's documents that are not yet approved — his own publish gate.

        Named, not counted: "3 documents outstanding" tells him there is work; "MCA451
        Internship — no document" tells him what it is.
        """
        rows = (
            await db.execute(
                sa_text(
                    "SELECT c.code, c.title, c.course_type, s.status "
                    "  FROM courses c "
                    "  LEFT JOIN LATERAL ("
                    "       SELECT sy.status FROM syllabi sy "
                    "        WHERE sy.course_id = c.id "
                    "        ORDER BY sy.version DESC LIMIT 1"
                    "  ) s ON true "
                    " WHERE c.program_id = :p "
                    "   AND c.course_type IN ('INTERNSHIP', 'MINI_PROJECT', "
                    "                         'MAJOR_PROJECT', 'SEMINAR') "
                    " ORDER BY c.semester, c.code"
                ),
                {"p": str(program_id)},
            )
        ).fetchall()

        return [
            f"{r.code} {r.title} ("
            + ("no document yet" if r.status is None else f"{r.status.lower()}")
            + ")"
            for r in rows
            if r.status not in ("APPROVED", "LOCKED")
        ]

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
                new_program.id, b.semester, b.name, b.description, created_by,
                credits=b.credits, db=db,
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

            # Carry the official syllabi forward as editable DRAFT copies.
            #
            # Without this, a new version starts with no syllabi at all, and
            # correcting a single typo in one subject would force the Board to
            # AI-regenerate all forty-odd from scratch — throwing away every
            # edit it made to the other thirty-nine. The Board should revise a
            # version, not rebuild it.
            #
            # v1's syllabi are not touched, and cannot be: each copy hangs off
            # v2's own brand-new course row, so the two versions share nothing.
            # Immutability holds by construction rather than by a guard.
            await ProgramService._carry_syllabi_forward(
                old_to_new, created_by=created_by, db=db,
            )

        await db.commit()
        return new_program

    @staticmethod
    async def _carry_syllabi_forward(
        old_to_new_course: dict[UUID, UUID],
        *,
        created_by: UUID,
        db: AsyncSession,
    ) -> int:
        """Copy each old course's official syllabus onto its new-version course.

        Takes the latest syllabus per course — approved or locked for a published
        curriculum, but a draft is copied too, so forking a curriculum the Board
        was midway through does not lose its work. Returns how many were copied.
        """
        from app.modules.m02_syllabus.repository import SyllabusRepository
        from app.modules.m02_syllabus.service import _deep_fork

        copied = 0
        for old_course_id, new_course_id in old_to_new_course.items():
            existing = await SyllabusRepository.list_by_course(old_course_id, db=db)
            if not existing:
                continue
            latest = max(existing, key=lambda s: s.version)
            await _deep_fork(
                latest.id,
                new_version=1,          # v2's course has no syllabus history yet
                created_by=created_by,
                change_note="Carried forward from the previous curriculum version.",
                target_course_id=new_course_id,
                db=db,
            )
            copied += 1

        if copied:
            logger.info("m01.fork: carried %d syllabus/es forward to the new version", copied)
        return copied

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
        await _require_editable_status(program_id, db=db)
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
        await _require_editable_status(program_id, db=db)
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
        await _require_editable_status(program_id, db=db)
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
    async def _reject_basket_placeholder(
        title: str | None,
        basket_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> None:
        """A slot is not a subject, and it may not enter `courses` by any door.

        Refused here rather than cleaned up later: a placeholder course takes a course
        code, is handed an official syllabus to generate, and stands in the approve
        gate blocking a curriculum until somebody approves a syllabus for a subject
        that nobody teaches.
        """
        basket_name = None
        if basket_id is not None:
            basket = await ElectiveBasketRepository.get_by_id(basket_id, db=db)
            basket_name = basket.name if basket else None

        if is_basket_placeholder(title, basket_name):
            raise ProgramServiceError(
                "BASKET_IS_NOT_A_COURSE", placeholder_message(title), 422,
            )

    @staticmethod
    async def add_course(
        program_id: UUID,
        payload: CourseCreate,
        *,
        db: AsyncSession,
    ) -> Course:
        await _require_editable_status(program_id, db=db)
        await ProgramService._reject_basket_placeholder(
            payload.title, payload.elective_basket_id, db=db,
        )
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

        # A rename is the other way a slot gets into `courses`: an ordinary subject,
        # retitled "Elective 2" by someone tidying up the structure. Checked against
        # the basket the course will be in AFTER this edit, not the one it is in now.
        if "title" in updates or "elective_basket_id" in updates:
            await ProgramService._reject_basket_placeholder(
                updates.get("title", course.title),
                updates.get("elective_basket_id", course.elective_basket_id),
                db=db,
            )

        updates["updated_at"] = datetime.now(timezone.utc)
        updated = await CourseRepository.update(course_id, updates, db=db)

        # If this edit moved anything the official syllabus is built on, the
        # Board's sign-off on that syllabus no longer means anything — it was
        # approved against a course that has since changed. Send it back to DRAFT
        # so the Board re-reads it; the approve gate then blocks the curriculum
        # until they do. In the SAME transaction as the edit: a crash between the
        # two would leave an approved syllabus describing a course that had moved.
        if _SYLLABUS_BEARING_FIELDS & updates.keys():
            from app.modules.m02_syllabus.service import SyllabusService
            await SyllabusService.invalidate_for_course(course_id, db=db)

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
            description=payload.description, created_by_user_id=created_by,
            credits=payload.credits, db=db,
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
    # Elective slot lifecycle + choices.
    #
    # These deliberately do NOT go through _require_editable_status. A slot's
    # choices are a catalogue concern with their own lifecycle: the Dean must be
    # able to fill in what Elective 1 offers this year on a program that was
    # published long ago. What stays frozen with the program is the slot's
    # *definition* (name, credits, semester), because those feed compliance and
    # the program credit total -- see add_basket/update_basket above.
    # ------------------------------------------------------------------

    @staticmethod
    async def _load_slot(basket_id: UUID, program_id: UUID, *, db: AsyncSession) -> ElectiveBasket:
        basket = await ElectiveBasketRepository.get_by_id(basket_id, db=db)
        if basket is None or basket.program_id != program_id:
            raise ProgramServiceError("NOT_FOUND", "Elective slot not found in this program.", 404)
        return basket

    @staticmethod
    async def _require_slot_draft(basket_id: UUID, program_id: UUID, *, db: AsyncSession) -> ElectiveBasket:
        slot = await ProgramService._load_slot(basket_id, program_id, db=db)

        # The curriculum lock beats the slot's own lifecycle. Once the Board has
        # approved the curriculum, an elective slot's COMPOSITION is frozen
        # forever: an option is a real subject a student sits and is examined in,
        # so adding one to a locked curriculum would smuggle in a course that
        # never had a Board-approved syllabus — and could never be given one,
        # because the curriculum is locked. That is the one hole through which a
        # subject could reach students without ever passing the Board.
        #
        # The slot's REGISTRATION lifecycle (status: DRAFT/PUBLISHED/OPEN/CLOSED)
        # keeps moving on a published curriculum — the Dean still opens and closes
        # student choice each year. What can never change again is WHICH subjects
        # the slot offers.
        if slot.locked_at is not None:
            raise ProgramServiceError(
                "CURRICULUM_LOCKED",
                f"{slot.name} belongs to an approved curriculum and its subjects are "
                "locked permanently. No elective may be added or removed after the "
                "curriculum is approved — every subject a student can take must have "
                "passed through the Board. Create a new curriculum version instead.",
                409,
            )

        if slot.status != ElectiveSlotStatus.DRAFT.value:
            raise ProgramServiceError(
                "SLOT_LOCKED",
                f"{slot.name} is {slot.status.lower()}; its choices can no longer be changed. "
                f"Choices are only editable while the slot is a draft.",
                409,
            )
        return slot

    @staticmethod
    async def add_choice(
        program_id: UUID,
        basket_id: UUID,
        payload: ElectiveChoiceCreate,
        *,
        db: AsyncSession,
    ) -> Course:
        """Create a real Course as one interchangeable option inside a slot.

        The code is generated, never supplied: a Dean should not have to know
        that MCA305 is taken. Credits default to the slot's own weight, since a
        student earns the slot's credits whichever option they take.
        """
        slot = await ProgramService._require_slot_draft(basket_id, program_id, db=db)
        program = await ProgramRepository.get_by_id(program_id, db=db)
        if program is None:
            raise ProgramServiceError("NOT_FOUND", "Program not found.", 404)

        # The same rule, one level down. A choice called "Elective 1" inside the
        # basket "Elective 1" is the slot listing itself as its own alternative.
        await ProgramService._reject_basket_placeholder(payload.title, basket_id, db=db)

        code = await generate_course_code(program_id, program.degree_type, slot.semester, db)
        course = await CourseRepository.create(
            program_id=program_id,
            code=code,
            title=payload.title,
            credits=payload.credits or slot.credits,
            semester=slot.semester,
            course_type=payload.course_type.value if payload.course_type else None,
            is_elective=True,
            elective_basket_id=basket_id,
            description=payload.description,
            db=db,
        )
        await db.commit()
        return course

    @staticmethod
    async def remove_choice(
        program_id: UUID,
        basket_id: UUID,
        course_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        """Delete an option outright. Unlike remove_course_from_basket (which
        merely unlinks and leaves an orphan elective course behind), a choice
        has no meaning outside its slot -- it was created for it."""
        await ProgramService._require_slot_draft(basket_id, program_id, db=db)
        course = await CourseRepository.get_by_id(course_id, db=db)
        if course is None or course.program_id != program_id or course.elective_basket_id != basket_id:
            raise ProgramServiceError("NOT_FOUND", "That subject is not a choice in this slot.", 404)
        await CourseRepository.delete(course_id, db=db)
        await db.commit()

    @staticmethod
    async def _transition_slot(
        program_id: UUID,
        basket_id: UUID,
        *,
        expected: ElectiveSlotStatus,
        target: ElectiveSlotStatus,
        updates: dict,
        db: AsyncSession,
    ) -> ElectiveBasket:
        slot = await ProgramService._load_slot(basket_id, program_id, db=db)
        if slot.status != expected.value:
            raise ProgramServiceError(
                "INVALID_SLOT_STATUS",
                f"{slot.name} is {slot.status.lower()}; this action requires it to be "
                f"{expected.value.lower()}.",
                409,
            )
        updated = await ElectiveBasketRepository.update(
            basket_id,
            {"status": target.value, "updated_at": datetime.now(timezone.utc), **updates},
            db=db,
        )
        await db.commit()
        return updated

    @staticmethod
    async def publish_slot(
        program_id: UUID, basket_id: UUID, published_by: UUID, *, db: AsyncSession,
    ) -> ElectiveBasket:
        """Freeze the choice list and make the slot visible to students. A slot
        with no choices would show students an empty question, so it is refused."""
        slot = await ProgramService._load_slot(basket_id, program_id, db=db)
        choices = await CourseRepository.list_by_basket(basket_id, db=db)
        if not choices:
            raise ProgramServiceError(
                "SLOT_EMPTY",
                f"{slot.name} has no choices yet. Add at least one subject before publishing.",
                422,
            )
        return await ProgramService._transition_slot(
            program_id, basket_id,
            expected=ElectiveSlotStatus.DRAFT, target=ElectiveSlotStatus.PUBLISHED,
            updates={
                "published_at": datetime.now(timezone.utc),
                "published_by_user_id": published_by,
            },
            db=db,
        )

    @staticmethod
    async def open_slot_registration(
        program_id: UUID, basket_id: UUID, *, db: AsyncSession,
    ) -> ElectiveBasket:
        return await ProgramService._transition_slot(
            program_id, basket_id,
            expected=ElectiveSlotStatus.PUBLISHED, target=ElectiveSlotStatus.OPEN,
            updates={"registration_opened_at": datetime.now(timezone.utc)},
            db=db,
        )

    @staticmethod
    async def close_slot_registration(
        program_id: UUID, basket_id: UUID, *, db: AsyncSession,
    ) -> ElectiveBasket:
        """The roster becomes final: students can no longer switch, and the
        faculty teaching each option now has a stable class list."""
        return await ProgramService._transition_slot(
            program_id, basket_id,
            expected=ElectiveSlotStatus.OPEN, target=ElectiveSlotStatus.CLOSED,
            updates={"registration_closed_at": datetime.now(timezone.utc)},
            db=db,
        )

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
        slot_nodes = await _build_elective_slot_nodes(program_id, db=db)
        program_node = ProgramNode(
            degree_type=program.degree_type,
            duration_years=program.duration_years,
            total_credits=program.total_credits,
            outcome_count=len(outcomes),
        )
        return run_compliance_check(program_node, course_nodes, slot_nodes)
