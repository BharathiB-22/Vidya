"""
M08 Exam Setter — Service layer.

Architecture contract:
  - All business logic here; router is pure HTTP glue.
  - ExamServiceError carries code, message, status_code for HTTP translation.
  - Celery task dispatch via TaskJobPublicRepository.
  - Three human gates enforced here AND in the repository:
      ExamService.submit_for_review() → only way status reaches SUBMITTED (Gate 1)
      ExamService.board_decide()      → only way status reaches BOARD_APPROVED / BOARD_RETURNED (Gate 2)
      ExamService.seal()              → only way status reaches SEALED (Gate 3)
  - Celery tasks may only advance status to GENERATED (generate task) or RELEASED (release task).
  - Model answers and correct_option are NEVER returned when status == SEALED.
  - Questions are NEVER returned when status == SEALED (forbidden at service level).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m08_exam_setter.models import (
    ExamPaperStatus,
    ExamWorkflow,
    InternalMarkStatus,
    InternalMarksSummary,
)
from app.modules.m08_exam_setter.repository import (
    BloomsRepository,
    ExamPaperRepository,
    ExamQuestionRepository,
    InternalMarksRepository,
    QuestionBankRepository,
    TaskJobPublicRepository,
)
from app.modules.m08_exam_setter.schemas import (
    BoardDecisionRequest,
    ExamPaperCreate,
    ExamQuestionUpdate,
    InternalMarksCreate,
    InternalMarksUpdate,
    ManualQuestionCreate,
    QuestionReorderRequest,
    ScrutinizerAssignRequest,
    ScrutinizerDecisionRequest,
    SealRequest,
)

logger = logging.getLogger("vidya.service.m08")


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------

class ExamServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# ExamService
# ---------------------------------------------------------------------------

class ExamService:

    # -----------------------------------------------------------------------
    # Ownership / editability guard (shared by all content mutations)
    # -----------------------------------------------------------------------

    _EDITABLE_STATUSES = (
        ExamPaperStatus.GENERATED.value,
        ExamPaperStatus.BOARD_RETURNED.value,
    )

    # A paper may be deleted only while Faculty owns it, and only in the three
    # pre-submission states the workflow allows: the initial record (DRAFT), a
    # completed generation (GENERATED), and a paper the reviewer handed back
    # (BOARD_RETURNED — ownership returns to Faculty). Never after a successful
    # submission.
    #
    # Every excluded state is excluded for a concrete reason, not by omission:
    #   GENERATING     — a Celery job is live; deleting the row orphans it.
    #   FAILED         — a failed generation is retried, not discarded (a delete
    #                    here is a separate decision the product owner has not
    #                    included in the allowed set).
    #   SUBMITTED      — ownership has transferred to the Dean/Board.
    #   BOARD_APPROVED — approved for locking; no longer the owner's to discard.
    #   SEALED         — locked exam material.
    #   RELEASED       — a released paper is a record, not a draft.
    _DELETABLE_STATUSES = (
        ExamPaperStatus.DRAFT.value,
        ExamPaperStatus.GENERATED.value,
        ExamPaperStatus.BOARD_RETURNED.value,
    )

    @staticmethod
    def _assert_can_edit(paper, actor_id: UUID, actor_role: str) -> None:
        """Guard content mutations (add/edit/delete/reorder).

        Status must be editable, AND the actor must own the paper:
          - INTERNAL papers belong to their Faculty creator (owner only).
          - BOARD_EXAM papers belong to the Board (any BOARD/ADMIN), while the
            faculty creator may still edit their own draft before it is submitted.
        """
        if paper.status not in ExamService._EDITABLE_STATUSES:
            raise ExamServiceError(
                "INVALID_STATUS",
                f"Questions can only be modified when the paper is GENERATED or "
                f"returned for edits (current: {paper.status!r}).",
            )
        if actor_role == "ADMIN":
            return
        if paper.exam_workflow == ExamWorkflow.INTERNAL.value:
            if paper.created_by != actor_id:
                raise ExamServiceError("FORBIDDEN", "You do not own this paper.", 403)
        else:  # BOARD_EXAM
            if actor_role == "BOARD":
                return
            if paper.created_by != actor_id:
                raise ExamServiceError("FORBIDDEN", "You do not own this paper.", 403)

    # -----------------------------------------------------------------------
    # Create
    # -----------------------------------------------------------------------

    @staticmethod
    async def create(
        payload: ExamPaperCreate,
        *,
        created_by: UUID,
        creator_role: str = "FACULTY",
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ):
        """
        Create an ExamPaper record.

        AI mode dispatches the generation Celery task (returns (paper, job_id)).
        MANUAL mode creates an empty, immediately-editable paper — no Celery, no
        LLM — and returns (paper, None).
        """
        # Verify the course exists in this tenant before creating the paper
        from sqlalchemy import select as _select
        from app.modules.m01_program_advisor.models import Course as _Course
        course_result = await db.execute(
            _select(_Course).where(_Course.id == payload.course_id)
        )
        if course_result.scalar_one_or_none() is None:
            raise ExamServiceError(
                "COURSE_NOT_FOUND",
                "The selected course was not found. Please select a valid course from the dropdown.",
                404,
            )

        # Subject restriction: a FACULTY may only set papers for subjects assigned
        # to them. BOARD/ADMIN are unrestricted (they own semester papers).
        if creator_role == "FACULTY":
            # Semester-End papers are set centrally by the Board alone. Faculty may
            # create internal papers (and non-final board papers), but never an
            # End-Semester paper. This is enforced here, at the create gate.
            if (payload.exam_type or "").upper() == "END_SEM":
                raise ExamServiceError(
                    "FORBIDDEN",
                    "Semester-End papers are created by the Board only. "
                    "Faculty cannot create an End-Semester paper.",
                    403,
                )
            from app.modules.m_academics.faculty_scope import faculty_teaches_course
            if not await faculty_teaches_course(created_by, payload.course_id, db):
                raise ExamServiceError(
                    "NOT_ASSIGNED",
                    "You can only create question papers for subjects assigned to you.",
                    403,
                )

        # Units come from the course's approved syllabus and nowhere else. Without
        # one there are no units, so a paper here could only be built on invented
        # ones — which would look real to the faculty and be about a syllabus that
        # does not exist. Block it instead.
        await ExamService._assert_units_exist_in_syllabus(
            payload.course_id, list(payload.units_included or []), db=db
        )

        section_config_data = (
            [s.model_dump() for s in payload.section_config]
            if payload.section_config else None
        )
        blueprint_data = (
            [b.model_dump() for b in payload.blueprint]
            if payload.blueprint else None
        )
        paper = await ExamPaperRepository.create(
            course_id=payload.course_id,
            created_by=created_by,
            title=payload.title,
            exam_type=payload.exam_type,
            exam_workflow=payload.exam_workflow.value,
            total_marks=payload.total_marks,
            duration_mins=payload.duration_mins,
            units_included=payload.units_included,
            question_format=payload.question_format.model_dump() if payload.question_format else {},
            requested_dist=payload.requested_dist.model_dump(),
            section_config=section_config_data,
            blueprint=blueprint_data,
            template_type=payload.template_type,
            template_definition=payload.template_definition,
            special_instructions=payload.special_instructions,
            creation_mode=payload.creation_mode,
            db=db,
        )
        await db.commit()
        await db.refresh(paper)

        # MANUAL mode: no AI, no Celery — land the paper directly in GENERATED so
        # the manual builder opens on an empty, editable paper.
        if payload.creation_mode == "MANUAL":
            await ExamPaperRepository.set_status(
                paper.id, ExamPaperStatus.GENERATED.value, db=db
            )
            await db.commit()
            await db.refresh(paper)
            return paper, None

        # Dispatch Celery generation task
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as pub_db:
            job_id = await TaskJobPublicRepository.create(
                task_type="generate_exam_paper",
                queue_name="heavy",
                tenant_id=tenant_id,
                payload={"paper_id": str(paper.id), "schema_name": schema_name},
                db=pub_db,
            )
            await pub_db.commit()

        await ExamPaperRepository.set_generation_job(paper.id, job_id=job_id, db=db)
        await db.commit()

        try:
            from app.workers.heavy.generate_exam_paper import generate_exam_paper
            generate_exam_paper.apply_async(
                kwargs={
                    "job_id":      str(job_id),
                    "paper_id":    str(paper.id),
                    "schema_name": schema_name,
                }
            )
        except Exception as exc:
            logger.error(
                "Failed to dispatch exam generation task for paper %s: %s",
                paper.id, exc,
            )
            await ExamPaperRepository.set_failed(
                paper.id,
                reason=f"Task queue unavailable: {exc}",
                db=db,
            )
            await db.commit()
            raise ExamServiceError(
                "QUEUE_UNAVAILABLE",
                "Question generation could not be queued — the task worker appears to be offline. "
                "Start the Celery worker (celery -A app.workers.celery_app worker) and try again.",
                503,
            )

        return paper, job_id

    # -----------------------------------------------------------------------
    # Read
    # -----------------------------------------------------------------------

    @staticmethod
    async def get(paper_id: UUID, *, db: AsyncSession):
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)
        return paper

    @staticmethod
    async def get_questions(
        paper_id: UUID,
        *,
        set_label: str | None,
        include_answers: bool,
        db: AsyncSession,
    ) -> list:
        """
        Return questions for a paper.
        Raises SEALED_ACCESS if paper is sealed (questions inaccessible until release).
        Model answers stripped unless include_answers=True (role-gated by router).
        """
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        if paper.status == ExamPaperStatus.SEALED.value:
            raise ExamServiceError(
                "SEALED_ACCESS",
                "Exam paper is sealed and inaccessible until the release date.",
                403,
            )

        questions = await ExamQuestionRepository.list_by_paper(
            paper_id, set_label=set_label, db=db
        )

        if not include_answers:
            # Strip model answer and correct_option for non-privileged views
            for q in questions:
                q.model_answer   = None
                q.correct_option = None

        return questions

    @staticmethod
    async def list_for_faculty(
        created_by: UUID,
        *,
        status: str | None,
        offset: int,
        limit: int,
        db: AsyncSession,
    ):
        return await ExamPaperRepository.list_for_faculty(
            created_by, status=status, offset=offset, limit=limit, db=db
        )

    @staticmethod
    async def list_board_pending(*, offset: int, limit: int, db: AsyncSession):
        return await ExamPaperRepository.list_board_pending(offset=offset, limit=limit, db=db)

    @staticmethod
    async def list_all(
        *,
        status: str | None,
        workflow: str | None = None,
        offset: int,
        limit: int,
        db: AsyncSession,
    ):
        return await ExamPaperRepository.list_all(
            status=status, workflow=workflow, offset=offset, limit=limit, db=db
        )

    @staticmethod
    async def get_blooms_report(paper_id: UUID, *, db: AsyncSession):
        report = await BloomsRepository.get_by_paper(paper_id, db=db)
        if report is None:
            raise ExamServiceError(
                "NOT_FOUND",
                "Bloom's compliance report not yet generated for this paper.",
                404,
            )
        return report

    # -----------------------------------------------------------------------
    # Question editing
    # -----------------------------------------------------------------------

    @staticmethod
    async def update_question(
        paper_id: UUID,
        question_id: UUID,
        payload: ExamQuestionUpdate,
        *,
        editor_user_id: UUID,
        editor_role: str = "FACULTY",
        db: AsyncSession,
    ):
        """Owner edits an individual question while the paper is editable."""
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        ExamService._assert_can_edit(paper, editor_user_id, editor_role)

        question = await ExamQuestionRepository.get_by_id(question_id, db=db)
        if question is None or question.exam_paper_id != paper_id:
            raise ExamServiceError("NOT_FOUND", "Question not found in this paper.", 404)

        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        if not updates:
            raise ExamServiceError("NO_CHANGES", "No fields provided for update.")

        await ExamQuestionRepository.update_question(question_id, updates=updates, db=db)
        await db.commit()
        return await ExamQuestionRepository.get_by_id(question_id, db=db)

    @staticmethod
    async def delete_question(
        paper_id: UUID,
        question_id: UUID,
        *,
        actor_id: UUID | None = None,
        actor_role: str = "FACULTY",
        db: AsyncSession,
    ):
        """Owner removes a question (AI or manual) while the paper is editable."""
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        ExamService._assert_can_edit(paper, actor_id, actor_role)

        question = await ExamQuestionRepository.get_by_id(question_id, db=db)
        if question is None or question.exam_paper_id != paper_id:
            raise ExamServiceError("NOT_FOUND", "Question not found in this paper.", 404)

        await ExamQuestionRepository.delete(question_id, db=db)
        await db.commit()

    # -----------------------------------------------------------------------
    # Delete whole paper (Faculty ownership window)
    # -----------------------------------------------------------------------

    @staticmethod
    def _assert_can_delete(paper, actor_id: UUID, actor_role: str) -> None:
        """Guard whole-paper deletion.

        Two independent gates, reported with distinct codes so the caller — and
        the UI — can tell "wrong state" from "not yours":

          409 INVALID_STATUS — the paper is in a state Faculty no longer owns
                               (generating, submitted, approved, sealed, released).
          403 FORBIDDEN      — the state is fine but the actor is not the owner.

        Deletion is ownership-by-CREATOR, in both workflows — deliberately
        stricter than _assert_can_edit, which additionally lets any BOARD user
        edit a BOARD_EXAM paper. Delete is a Faculty-ownership action: a paper is
        the Faculty creator's to discard while it is under their control, and the
        Board role alone does not grant it. (A BOARD user who created a paper is
        still its creator and so may delete that one, via the same check.)
        ADMIN stays unrestricted, consistent with the rest of the platform.
        """
        if paper.status not in ExamService._DELETABLE_STATUSES:
            raise ExamServiceError(
                "INVALID_STATUS",
                f"This paper cannot be deleted in its current state "
                f"({paper.status}). Delete is only allowed while it is a draft, "
                f"generated, failed, or returned for edits.",
                409,
            )
        if actor_role == "ADMIN":
            return
        if paper.created_by != actor_id:
            raise ExamServiceError("FORBIDDEN", "You do not own this paper.", 403)

    @staticmethod
    def _assert_can_finalize(paper, actor_id: UUID, actor_role: str) -> None:
        """Guard the seal and release steps — who owns a paper once it is approved.

        The two workflows finalise a paper differently, and this is the single
        rule that keeps them apart:

          INTERNAL   the Dean locks (seals) and releases the paper. Faculty hand
                     the paper off at submission and do not finalise it; the Dean
                     reviews (approve/return), then locks and — later, when they
                     choose — releases it. The Board has NO role in internal papers.
          BOARD_EXAM the Board locks (seals) and releases. Faculty hand the paper
                     off at submission and do not finalise it.

        ADMIN is unrestricted in both, consistent with the rest of the platform.
        Status is validated separately by the seal/force_release methods; this
        answers only "may this actor finalise this paper".
        """
        if actor_role == "ADMIN":
            return
        if paper.exam_workflow == ExamWorkflow.INTERNAL.value:
            if actor_role != "DEAN":
                raise ExamServiceError(
                    "FORBIDDEN",
                    "Only the Dean can lock or release an internal assessment paper.",
                    403,
                )
        else:  # BOARD_EXAM
            if actor_role != "BOARD":
                raise ExamServiceError(
                    "FORBIDDEN",
                    "Only the Board can lock or release a board examination paper.",
                    403,
                )

    @staticmethod
    async def delete_paper(
        paper_id: UUID,
        *,
        actor_id: UUID,
        actor_role: str = "FACULTY",
        db: AsyncSession,
    ):
        """Owner deletes a paper while it is still under Faculty control.

        Questions and the Bloom's report are removed by ON DELETE CASCADE on
        their FKs to exam_papers, so deleting the paper row is sufficient.
        """
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        ExamService._assert_can_delete(paper, actor_id, actor_role)

        await ExamPaperRepository.delete(paper_id, db=db)
        await db.commit()

    # -----------------------------------------------------------------------
    # Manual builder: add question / reorder
    # -----------------------------------------------------------------------

    @staticmethod
    async def _assert_units_exist_in_syllabus(
        course_id, units_included: list[int], *, db: AsyncSession
    ) -> None:
        """Every unit on the paper must exist in the course's approved syllabus.

        The syllabus is the only source of units. This blocks two failures the
        faculty could not otherwise see: setting a paper for a course whose
        syllabus was never approved, and keeping a unit that the syllabus dropped
        in a later version.
        """
        from sqlalchemy import select as _select
        from sqlalchemy.orm import selectinload
        from app.modules.m02_syllabus.models import Syllabus

        result = await db.execute(
            _select(Syllabus)
            # Syllabus.units is lazy="select"; on an AsyncSession a lazy load
            # raises MissingGreenlet rather than emitting a query, so the
            # relationship has to be loaded up front.
            .options(selectinload(Syllabus.units))
            .where(Syllabus.course_id == course_id)
            .where(Syllabus.status.in_(["LOCKED", "APPROVED"]))
            .order_by(Syllabus.version.desc())
            .limit(1)
        )
        syllabus = result.scalar_one_or_none()
        if syllabus is None:
            raise ExamServiceError(
                "NO_APPROVED_SYLLABUS",
                "This course has no approved syllabus yet, so its units are not "
                "defined. A question paper can only be set against an approved "
                "syllabus.",
                409,
            )

        # syllabus.units are SyllabusUnit rows, not dicts — read the column.
        available = {
            int(u.unit_number)
            for u in (syllabus.units or [])
            if u.unit_number is not None
        }
        available.discard(0)
        if not available:
            raise ExamServiceError(
                "SYLLABUS_HAS_NO_UNITS",
                "The approved syllabus for this course defines no units.",
                409,
            )

        unknown = sorted(set(units_included) - available)
        if unknown:
            raise ExamServiceError(
                "UNIT_NOT_IN_SYLLABUS",
                f"Unit(s) {', '.join(str(u) for u in unknown)} are not in this "
                f"course's approved syllabus, which defines "
                f"{', '.join(str(u) for u in sorted(available))}.",
                400,
            )

    @staticmethod
    def _assert_question_has_a_block(paper, template_block_id: str | None) -> None:
        """A question on a templated paper must name the block it belongs to.

        The template is the paper's structure: a question with no block has no
        place to print, and the old behaviour — quietly collecting such questions
        into an "additional questions" bucket — printed a paper that was not the
        one the faculty built. Rejecting the write keeps paper and template in
        step. Legacy papers (no template) are unaffected.
        """
        from app.modules.m08_exam_setter.paper_template import normalise_definition

        doc = normalise_definition(getattr(paper, "template_definition", None))
        valid = {
            str(qd.get("id") or f"qd{di}")
            for sec in doc["sections"]
            for di, qd in enumerate(sec.get("definitions") or [])
        }
        if not valid:
            return
        if template_block_id not in valid:
            raise ExamServiceError(
                "TEMPLATE_BLOCK_REQUIRED",
                "This paper follows a template, so a question must say which "
                "section or question block it belongs to. Pick one and retry.",
                400,
            )

    @staticmethod
    async def add_question(
        paper_id: UUID,
        payload: ManualQuestionCreate,
        *,
        actor_id: UUID,
        actor_role: str,
        db: AsyncSession,
    ):
        """Add a hand-written question. Coexists with AI questions; ai_generated=False."""
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)
        ExamService._assert_can_edit(paper, actor_id, actor_role)

        data = payload.model_dump()
        if data.get("co_ids"):
            data["co_ids"] = [str(x) for x in data["co_ids"]]
        if data.get("options"):
            data["options"] = [o.model_dump() if hasattr(o, "model_dump") else o for o in data["options"]]
        ExamService._assert_question_has_a_block(paper, data.get("template_block_id"))
        next_order = (await ExamQuestionRepository.max_display_order(paper_id, db=db)) + 1
        question = await ExamQuestionRepository.add_one(
            paper_id, data=data, display_order=next_order, db=db
        )
        await db.commit()
        return await ExamQuestionRepository.get_by_id(question.id, db=db)

    @staticmethod
    async def duplicate_question(
        paper_id: UUID,
        question_id: UUID,
        *,
        actor_id: UUID,
        actor_role: str,
        db: AsyncSession,
    ):
        """Duplicate a question in place. The copy is inserted immediately after
        the original in display order; remaining questions shift down."""
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)
        ExamService._assert_can_edit(paper, actor_id, actor_role)

        source = await ExamQuestionRepository.get_by_id(question_id, db=db)
        if source is None or source.exam_paper_id != paper_id:
            raise ExamServiceError("NOT_FOUND", "Question not found in this paper.", 404)

        next_order = (await ExamQuestionRepository.max_display_order(paper_id, db=db)) + 1
        dup = await ExamQuestionRepository.copy_question(
            source, display_order=next_order, db=db
        )
        await db.flush()

        # Re-order so the copy sits right after its original.
        existing = await ExamQuestionRepository.list_by_paper(paper_id, db=db)
        ordered_ids = [q.id for q in existing if q.id != dup.id]
        idx = ordered_ids.index(source.id)
        ordered_ids.insert(idx + 1, dup.id)
        order_map = {qid: i for i, qid in enumerate(ordered_ids)}
        await ExamQuestionRepository.set_display_orders(order_map, db=db)

        await db.commit()
        return await ExamQuestionRepository.get_by_id(dup.id, db=db)

    @staticmethod
    async def reorder_questions(
        paper_id: UUID,
        payload: QuestionReorderRequest,
        *,
        actor_id: UUID,
        actor_role: str,
        db: AsyncSession,
    ):
        """Set display_order from the given ordered id list (drag & drop)."""
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)
        ExamService._assert_can_edit(paper, actor_id, actor_role)

        existing = await ExamQuestionRepository.list_by_paper(paper_id, db=db)
        existing_ids = {q.id for q in existing}
        if set(payload.ordered_ids) != existing_ids:
            raise ExamServiceError(
                "INVALID_REORDER",
                "The reorder list must contain exactly the paper's current question ids.",
            )
        order_map = {qid: idx for idx, qid in enumerate(payload.ordered_ids)}
        await ExamQuestionRepository.set_display_orders(order_map, db=db)
        await db.commit()
        return await ExamQuestionRepository.list_by_paper(paper_id, db=db)

    # -----------------------------------------------------------------------
    # Dean review (INTERNAL papers) — reuses the generic approved/returned states
    # -----------------------------------------------------------------------

    @staticmethod
    async def list_dean_pending(
        *, dean_user_id: UUID, dean_role: str, offset: int, limit: int, db: AsyncSession
    ):
        """INTERNAL papers awaiting Dean review, department-scoped for a DEAN."""
        course_ids: list[UUID] | None = None
        if dean_role == "DEAN":
            from sqlalchemy import select as _select
            from app.modules.m01_program_advisor.models import Course, Program
            from app.modules.m_academics.dean_scope import get_dean_program_ids
            governed = await get_dean_program_ids(dean_user_id, "DEAN", db)
            if governed is not None:
                rows = await db.execute(
                    _select(Course.id).join(Program, Program.id == Course.program_id)
                    .where(Program.acad_program_id.in_(governed))
                )
                course_ids = [r[0] for r in rows.all()]
        return await ExamPaperRepository.list_dean_pending(
            course_ids=course_ids, offset=offset, limit=limit, db=db
        )

    @staticmethod
    async def dean_decide(
        paper_id: UUID,
        payload: BoardDecisionRequest,
        *,
        dean_user_id: UUID,
        dean_role: str,
        db: AsyncSession,
    ):
        """The Dean approves or returns an INTERNAL paper. Reuses the generic
        approved/returned states and the shared review-comment field — the only
        difference from the Board flow is *who* is authorised (by exam_workflow)."""
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        if paper.exam_workflow != ExamWorkflow.INTERNAL.value:
            raise ExamServiceError(
                "INVALID_WORKFLOW",
                "This is a Semester paper — it is reviewed by the Board, not the Dean.",
                400,
            )
        if paper.status != ExamPaperStatus.SUBMITTED.value:
            raise ExamServiceError(
                "INVALID_STATUS",
                f"Dean decision requires paper status SUBMITTED (current: {paper.status!r}).",
            )

        # Department scoping: a DEAN may only decide on papers for programs they govern.
        if dean_role == "DEAN":
            from sqlalchemy import select as _select
            from app.modules.m01_program_advisor.models import Course, Program
            from app.modules.m_academics.dean_scope import get_dean_program_ids
            governed = await get_dean_program_ids(dean_user_id, "DEAN", db)
            if governed is not None:
                row = (await db.execute(
                    _select(Program.acad_program_id).join(Course, Course.program_id == Program.id)
                    .where(Course.id == paper.course_id)
                )).scalar_one_or_none()
                if row not in governed:
                    raise ExamServiceError(
                        "NOT_IN_SCOPE", "You may only review papers for programs you govern.", 403
                    )

        await ExamPaperRepository.set_board_decision(
            paper_id,
            approved=payload.approved,
            approved_by=dean_user_id,
            board_comment=payload.board_comment,
            db=db,
        )
        await db.commit()
        return await ExamPaperRepository.get_by_id(paper_id, db=db)

    # -----------------------------------------------------------------------
    # GATE 1 — Faculty submits for Board review
    # -----------------------------------------------------------------------

    @staticmethod
    async def submit_for_review(
        paper_id: UUID,
        *,
        faculty_user_id: UUID,
        db: AsyncSession,
    ):
        """
        HUMAN GATE 1: Faculty submits paper for Examination Board review.
        Only the creator can submit. Status must be GENERATED or BOARD_RETURNED.
        """
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        if paper.created_by != faculty_user_id:
            raise ExamServiceError(
                "FORBIDDEN", "Only the paper creator can submit it for review.", 403
            )

        # Both workflows submit through here. Routing to the correct reviewer is
        # by exam_workflow: INTERNAL → Dean queue, BOARD_EXAM → Board queue.

        submittable = (
            ExamPaperStatus.GENERATED.value,
            ExamPaperStatus.BOARD_RETURNED.value,
        )
        if paper.status not in submittable:
            raise ExamServiceError(
                "INVALID_STATUS",
                f"Paper must be GENERATED or BOARD_RETURNED to submit "
                f"(current: {paper.status!r}).",
            )

        # Must have at least one question
        questions = await ExamQuestionRepository.list_by_paper(paper_id, db=db)
        if not questions:
            raise ExamServiceError(
                "NO_QUESTIONS",
                "Cannot submit a paper with no questions. Generate questions first.",
            )

        await ExamPaperRepository.set_submitted(paper_id, db=db)
        await db.commit()
        return await ExamPaperRepository.get_by_id(paper_id, db=db)

    # -----------------------------------------------------------------------
    # GATE 2 — Examination Board approves or returns
    # -----------------------------------------------------------------------

    @staticmethod
    async def board_decide(
        paper_id: UUID,
        payload: BoardDecisionRequest,
        *,
        board_user_id: UUID,
        db: AsyncSession,
    ):
        """
        HUMAN GATE 2: the Board approves or returns a SEMESTER (BOARD_EXAM) paper.
        A faculty draft arrives as SUBMITTED; a board-created paper may be approved
        directly from GENERATED ("publish directly"). Internal papers go to the
        Dean via dean_decide(), never here.
        """
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        if paper.exam_workflow != ExamWorkflow.BOARD_EXAM.value:
            raise ExamServiceError(
                "INVALID_WORKFLOW",
                "This is an Internal paper — it is reviewed by the Dean, not the Board.",
                400,
            )

        allowed = (ExamPaperStatus.SUBMITTED.value, ExamPaperStatus.GENERATED.value)
        if paper.status not in allowed:
            raise ExamServiceError(
                "INVALID_STATUS",
                f"Board decision requires status SUBMITTED or GENERATED (current: {paper.status!r}).",
            )

        await ExamPaperRepository.set_board_decision(
            paper_id,
            approved=payload.approved,
            approved_by=board_user_id,
            board_comment=payload.board_comment,
            db=db,
        )

        if payload.approved:
            questions = await ExamQuestionRepository.list_by_paper(paper_id, db=db)
            await QuestionBankRepository.promote_from_paper(
                paper_id=paper_id,
                course_id=paper.course_id,
                questions=questions,
                is_approved=True,
                db=db,
            )

        await db.commit()
        return await ExamPaperRepository.get_by_id(paper_id, db=db)

    # -----------------------------------------------------------------------
    # GATE 3 — Board seals the paper
    # -----------------------------------------------------------------------

    @staticmethod
    async def seal(
        paper_id: UUID,
        payload: SealRequest,
        *,
        sealing_user_id: UUID,
        actor_role: str = "BOARD",
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ):
        """
        HUMAN GATE 3: lock (seal) the paper with AES encryption. Paper must be
        BOARD_APPROVED. This records a PLANNED release date but does NOT schedule
        an automatic release — release is a separate human decision (see
        force_release), taken by the Dean (INTERNAL) or the Board (BOARD_EXAM)
        whenever they choose.

        WHO may seal is workflow-dependent (see _assert_can_finalize): the Dean
        for an INTERNAL paper, the Board for a BOARD_EXAM paper. The router gates
        the endpoint to DEAN/BOARD/ADMIN; the fine-grained rule is here, where the
        paper's workflow is known.
        """
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        ExamService._assert_can_finalize(paper, sealing_user_id, actor_role)

        if paper.status != ExamPaperStatus.BOARD_APPROVED.value:
            raise ExamServiceError(
                "INVALID_STATUS",
                f"Paper must be BOARD_APPROVED to seal (current: {paper.status!r}).",
            )

        # Collect all questions + model answers for encryption
        questions = await ExamQuestionRepository.list_by_paper(paper_id, db=db)
        paper_payload = {
            "paper_id":    str(paper_id),
            "title":       paper.title,
            "total_marks": paper.total_marks,
            "questions": [
                {
                    "id":             str(q.id),
                    "question_text":  q.question_text,
                    "bloom_level":    q.bloom_level,
                    "question_type":  q.question_type,
                    "unit_number":    q.unit_number,
                    "marks":          float(q.marks),
                    "options":        q.options,
                    "correct_option": q.correct_option,
                    "model_answer":   q.model_answer,
                    "marking_scheme": q.marking_scheme,
                    "set_membership": q.set_membership,
                }
                for q in questions
            ],
        }

        from app.modules.m08_exam_setter.paper_sealer import seal as fernet_seal
        encrypted_bytes, key_ref = fernet_seal(paper_payload)

        # Store encrypted blob in S3
        s3_key = await ExamService._store_encrypted_blob(
            tenant_id=tenant_id,
            paper_id=paper_id,
            encrypted_bytes=encrypted_bytes,
        )

        # Record the PLANNED release date only. NO automatic release is scheduled:
        # release is a human decision taken later by the Dean (INTERNAL) or the
        # Board (BOARD_EXAM) via force_release. release_job_id stays NULL because
        # no timed task exists.
        await ExamPaperRepository.set_sealed(
            paper_id,
            release_at=payload.release_at,
            encrypted_blob_key=s3_key,
            encryption_key_ref=key_ref,
            release_job_id=None,
            db=db,
        )
        await db.commit()

        return await ExamPaperRepository.get_by_id(paper_id, db=db)

    @staticmethod
    async def _store_encrypted_blob(
        *,
        tenant_id: UUID,
        paper_id: UUID,
        encrypted_bytes: bytes,
    ) -> str:
        """Upload encrypted paper blob to S3. Returns S3 object key."""
        s3_key = f"exam_papers/{tenant_id}/{paper_id}/encrypted.bin"
        try:
            from app.core.storage.client import get_storage_client
            client = get_storage_client()
            import io
            await client.upload_fileobj(
                io.BytesIO(encrypted_bytes),
                key=s3_key,
                content_type="application/octet-stream",
            )
        except Exception as exc:
            logger.warning(
                "S3 upload failed for sealed paper %s: %s — storing key only.", paper_id, exc
            )
        return s3_key

    # -----------------------------------------------------------------------
    # Release (called by Celery task only)
    # -----------------------------------------------------------------------

    @staticmethod
    async def release(paper_id: UUID, *, schema_name: str, db: AsyncSession):
        """
        Called by release_exam_paper Celery task at scheduled release_at time.
        Transitions status SEALED → RELEASED.
        This is a system action, not a human gate.
        """
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        if paper.status != ExamPaperStatus.SEALED.value:
            # Already released or in unexpected state — log and return
            logger.warning(
                "Release called on paper %s with status %s (expected SEALED).",
                paper_id, paper.status,
            )
            return paper

        # Verify release_at has passed
        now = datetime.now(timezone.utc)
        if paper.release_at and paper.release_at > now:
            raise ExamServiceError(
                "TOO_EARLY",
                f"Release time {paper.release_at.isoformat()} has not passed yet.",
                400,
            )

        await ExamPaperRepository.set_released(paper_id, db=db)
        await db.commit()
        return await ExamPaperRepository.get_by_id(paper_id, db=db)

    # -----------------------------------------------------------------------
    # Force-release — Board-triggered immediate release
    # -----------------------------------------------------------------------

    @staticmethod
    async def force_release(
        paper_id: UUID,
        *,
        actor_id: UUID | None = None,
        actor_role: str = "BOARD",
        schema_name: str,
        db: AsyncSession,
    ):
        """
        Human-triggered immediate release. Transitions SEALED → RELEASED,
        bypassing the scheduled release_at time.

        WHO may release matches WHO may seal (see _assert_can_finalize): the
        Faculty owner for an INTERNAL paper, the Board for a BOARD_EXAM paper.
        """
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        ExamService._assert_can_finalize(paper, actor_id, actor_role)

        if paper.status != ExamPaperStatus.SEALED.value:
            raise ExamServiceError(
                "INVALID_STATUS",
                f"Paper must be SEALED to release immediately (current: {paper.status!r}).",
            )

        await ExamPaperRepository.set_released(paper_id, db=db)
        await db.commit()
        return await ExamPaperRepository.get_by_id(paper_id, db=db)

    # -----------------------------------------------------------------------
    # INTERNAL workflow note
    # -----------------------------------------------------------------------
    # Internal assessment papers are NOT self-approved by Faculty. They follow the
    # same Faculty → submit → reviewer → approve path as board papers; the only
    # difference is the reviewer (the Dean, via dean_decide) and the finaliser (the
    # Dean, via seal/force_release). There is deliberately no faculty_approve here.

    # -----------------------------------------------------------------------
    # H-35: Scrutinizer — optional Gate 1.5 (BOARD_EXAM only)
    # -----------------------------------------------------------------------

    @staticmethod
    async def assign_scrutinizer(
        paper_id: UUID,
        payload: ScrutinizerAssignRequest,
        *,
        assigning_user_id: UUID,
        db: AsyncSession,
    ):
        """Assign a second-faculty scrutinizer to a BOARD_EXAM paper in SUBMITTED status."""
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        if paper.exam_workflow != ExamWorkflow.BOARD_EXAM.value:
            raise ExamServiceError(
                "INVALID_WORKFLOW",
                "Scrutinizers can only be assigned to BOARD_EXAM papers.",
                400,
            )

        if paper.status != ExamPaperStatus.SUBMITTED.value:
            raise ExamServiceError(
                "INVALID_STATUS",
                f"Paper must be SUBMITTED to assign a scrutinizer "
                f"(current: {paper.status!r}).",
            )

        await ExamPaperRepository.set_scrutinizer(
            paper_id, scrutinizer_id=payload.scrutinizer_id, db=db
        )
        await db.commit()
        return await ExamPaperRepository.get_by_id(paper_id, db=db)

    @staticmethod
    async def scrutinize(
        paper_id: UUID,
        payload: ScrutinizerDecisionRequest,
        *,
        scrutinizer_user_id: UUID,
        db: AsyncSession,
    ):
        """
        Scrutinizer approves or returns a paper (Gate 1.5, BOARD_EXAM only).
        Approved: stays SUBMITTED for Board to act.
        Returned: transitions to BOARD_RETURNED for faculty revision.
        """
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        if paper.scrutinizer_id != scrutinizer_user_id:
            raise ExamServiceError(
                "FORBIDDEN", "Only the assigned scrutinizer can submit a decision.", 403
            )

        if paper.status != ExamPaperStatus.SUBMITTED.value:
            raise ExamServiceError(
                "INVALID_STATUS",
                f"Paper must be SUBMITTED for scrutinizer review "
                f"(current: {paper.status!r}).",
            )

        await ExamPaperRepository.set_scrutinized(
            paper_id, comment=payload.scrutinizer_comment, db=db
        )

        if not payload.approved:
            await ExamPaperRepository.set_status(
                paper_id, ExamPaperStatus.BOARD_RETURNED.value, db=db
            )

        await db.commit()
        return await ExamPaperRepository.get_by_id(paper_id, db=db)

    # -----------------------------------------------------------------------
    # H-35: Section configuration
    # -----------------------------------------------------------------------

    @staticmethod
    async def configure_sections(
        paper_id: UUID,
        sections: list[dict],
        *,
        faculty_user_id: UUID,
        db: AsyncSession,
    ):
        """Update section_config. Only valid before submission."""
        paper = await ExamPaperRepository.get_by_id(paper_id, db=db)
        if paper is None:
            raise ExamServiceError("NOT_FOUND", "Exam paper not found.", 404)

        if paper.created_by != faculty_user_id:
            raise ExamServiceError(
                "FORBIDDEN", "Only the paper creator can configure sections.", 403
            )

        configurable = (
            ExamPaperStatus.DRAFT.value,
            ExamPaperStatus.GENERATED.value,
            ExamPaperStatus.BOARD_RETURNED.value,
        )
        if paper.status not in configurable:
            raise ExamServiceError(
                "INVALID_STATUS",
                f"Section config can only be changed before submission "
                f"(current: {paper.status!r}).",
            )

        await ExamPaperRepository.set_section_config(paper_id, section_config=sections, db=db)
        await db.commit()
        return await ExamPaperRepository.get_by_id(paper_id, db=db)

    # -----------------------------------------------------------------------
    # H-35: Question bank browse
    # -----------------------------------------------------------------------

    @staticmethod
    async def list_question_bank(
        course_id: UUID,
        *,
        bloom_level: str | None = None,
        question_type: str | None = None,
        unit_number: int | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ):
        items = await QuestionBankRepository.list_by_course(
            course_id,
            bloom_level=bloom_level,
            question_type=question_type,
            unit_number=unit_number,
            approved_only=True,
            offset=offset,
            limit=limit,
            db=db,
        )
        total = await QuestionBankRepository.count_by_course(
            course_id, approved_only=True, db=db
        )
        return items, total


# ---------------------------------------------------------------------------
# InternalMarksServiceError
# ---------------------------------------------------------------------------

class InternalMarksServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# InternalMarksService  (H-35 Addition 2)
# ---------------------------------------------------------------------------

class InternalMarksService:

    @staticmethod
    async def create_or_update(
        payload: InternalMarksCreate,
        *,
        faculty_user_id: UUID,
        db: AsyncSession,
    ) -> InternalMarksSummary:
        """Create a new IMS record or update marks on an existing PENDING record."""
        existing = await InternalMarksRepository.get_by_student_course(
            payload.student_id, payload.course_id,
            payload.semester, payload.academic_year,
            db=db,
        )
        if existing is not None:
            if existing.status == InternalMarkStatus.DEAN_LOCKED.value:
                raise InternalMarksServiceError(
                    "LOCKED",
                    "Internal marks are Dean-locked and cannot be modified.",
                    403,
                )
            skip_keys = {"student_id", "course_id", "semester", "academic_year"}
            updates = {
                k: v for k, v in payload.model_dump().items()
                if k not in skip_keys and v is not None
            }
            if updates:
                await InternalMarksRepository.update_marks(existing.id, updates=updates, db=db)
            await db.commit()
            return await InternalMarksRepository.get_by_id(existing.id, db=db)

        ims = await InternalMarksRepository.create(
            student_id=payload.student_id,
            course_id=payload.course_id,
            semester=payload.semester,
            academic_year=payload.academic_year,
            internal1_marks=payload.internal1_marks,
            internal2_marks=payload.internal2_marks,
            assignment_marks=payload.assignment_marks,
            attendance_marks=payload.attendance_marks,
            max_internal=payload.max_internal,
            db=db,
        )
        await db.commit()
        return await InternalMarksRepository.get_by_id(ims.id, db=db)

    @staticmethod
    async def update(
        ims_id: UUID,
        payload: InternalMarksUpdate,
        *,
        db: AsyncSession,
    ) -> InternalMarksSummary:
        ims = await InternalMarksRepository.get_by_id(ims_id, db=db)
        if ims is None:
            raise InternalMarksServiceError("NOT_FOUND", "Internal marks record not found.", 404)
        if ims.status == InternalMarkStatus.DEAN_LOCKED.value:
            raise InternalMarksServiceError(
                "LOCKED", "Dean-locked records cannot be modified.", 403
            )
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        if updates:
            await InternalMarksRepository.update_marks(ims_id, updates=updates, db=db)
            await db.commit()
        return await InternalMarksRepository.get_by_id(ims_id, db=db)

    @staticmethod
    async def submit(
        ims_id: UUID,
        *,
        faculty_user_id: UUID,
        db: AsyncSession,
    ) -> InternalMarksSummary:
        """
        HUMAN GATE 1: Faculty submits internal marks.
        Transitions PENDING → FACULTY_SUBMITTED.
        Computes and stores total_internal from components.
        """
        ims = await InternalMarksRepository.get_by_id(ims_id, db=db)
        if ims is None:
            raise InternalMarksServiceError("NOT_FOUND", "Internal marks record not found.", 404)

        if ims.status != InternalMarkStatus.PENDING.value:
            raise InternalMarksServiceError(
                "INVALID_STATUS",
                f"Marks must be PENDING to submit (current: {ims.status!r}).",
            )

        components = [
            ims.internal1_marks, ims.internal2_marks,
            ims.assignment_marks, ims.attendance_marks,
        ]
        total = sum(float(c) for c in components if c is not None)
        if total > ims.max_internal:
            raise InternalMarksServiceError(
                "TOTAL_EXCEEDS_MAX",
                f"Total internal marks {total} exceeds max_internal {ims.max_internal}.",
            )

        await InternalMarksRepository.set_submitted(
            ims_id,
            submitted_by=faculty_user_id,
            total_internal=total,
            db=db,
        )
        await db.commit()
        return await InternalMarksRepository.get_by_id(ims_id, db=db)

    @staticmethod
    async def lock(
        ims_id: UUID,
        *,
        dean_user_id: UUID,
        db: AsyncSession,
    ) -> InternalMarksSummary:
        """
        HUMAN GATE 2: Dean locks internal marks. FACULTY_SUBMITTED → DEAN_LOCKED.
        After locking, no further updates are permitted (enforced at service layer).
        """
        ims = await InternalMarksRepository.get_by_id(ims_id, db=db)
        if ims is None:
            raise InternalMarksServiceError("NOT_FOUND", "Internal marks record not found.", 404)

        if ims.status != InternalMarkStatus.FACULTY_SUBMITTED.value:
            raise InternalMarksServiceError(
                "INVALID_STATUS",
                f"Marks must be FACULTY_SUBMITTED to lock (current: {ims.status!r}).",
            )

        await InternalMarksRepository.set_locked(ims_id, locked_by=dean_user_id, db=db)
        await db.commit()
        return await InternalMarksRepository.get_by_id(ims_id, db=db)

    @staticmethod
    async def get(ims_id: UUID, *, db: AsyncSession) -> InternalMarksSummary:
        ims = await InternalMarksRepository.get_by_id(ims_id, db=db)
        if ims is None:
            raise InternalMarksServiceError("NOT_FOUND", "Internal marks record not found.", 404)
        return ims

    @staticmethod
    async def list_by_course(
        course_id: UUID,
        *,
        semester: int | None = None,
        academic_year: str | None = None,
        offset: int = 0,
        limit: int = 100,
        db: AsyncSession,
    ) -> tuple[list[InternalMarksSummary], int]:
        items = await InternalMarksRepository.list_by_course(
            course_id, semester=semester, academic_year=academic_year,
            offset=offset, limit=limit, db=db,
        )
        total = await InternalMarksRepository.count_by_course(
            course_id, semester=semester, academic_year=academic_year, db=db,
        )
        return items, total
