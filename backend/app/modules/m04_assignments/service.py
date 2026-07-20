"""
M04 Assignments — Service layer.

Architecture contract:
  - All business logic lives here; router is pure HTTP glue.
  - AssignmentServiceError carries code, message, status_code for HTTP translation.
  - No AI evaluation pipeline — assignments are manually graded by faculty only.
  - Marks/feedback are never written except by an explicit faculty grade action.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m04_assignments.models import (
    Assignment,
    AssignmentStatus,
    AssignmentSubmission,
)
from app.modules.m04_assignments.repository import (
    COURSEWORK_TARGET_ENTITY,
    AssignmentRepository,
    SubmissionRepository,
)
from app.modules.m04_assignments.schemas import AssignmentCreate, AssignmentUpdate

logger = logging.getLogger("vidya.service.m04")


class AssignmentServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


def _question_marks_total(questions) -> float:
    """Sum the per-question marks. Accepts either pydantic AssignmentQuestion
    objects (create/update payloads) or the plain dicts stored in JSONB."""
    total = 0.0
    for q in questions or []:
        m = getattr(q, "marks", None) if not isinstance(q, dict) else q.get("marks")
        total += float(m or 0)
    return total


def _assert_questions_match_max(questions, max_marks: float) -> None:
    """When structured questions are present, their marks must add up to the
    assignment's max_marks. Empty questions (paper upload or metadata-only) are
    left alone, so older assignments keep working untouched. A small tolerance
    absorbs float rounding on fractional marks."""
    if not questions:
        return
    total = _question_marks_total(questions)
    if abs(total - float(max_marks)) > 0.01:
        raise AssignmentServiceError(
            "QUESTION_MARKS_MISMATCH",
            f"The question marks add up to {total:g}, which must equal the "
            f"assignment's max marks ({float(max_marks):g}).",
        )


async def _require_assignment(assignment_id: UUID, *, db: AsyncSession) -> Assignment:
    obj = await AssignmentRepository.get_by_id(assignment_id, db=db)
    if obj is None:
        raise AssignmentServiceError("NOT_FOUND", "Assignment not found.", 404)
    return obj


async def _require_submission(submission_id: UUID, *, db: AsyncSession) -> AssignmentSubmission:
    obj = await SubmissionRepository.get_by_id(submission_id, db=db)
    if obj is None:
        raise AssignmentServiceError("NOT_FOUND", "Submission not found.", 404)
    return obj


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------
# Coursework belongs to the faculty who set it. Another faculty member has no
# business reading it, let alone publishing or closing it — they are a peer, not
# a supervisor. The Dean owns the department and Admin owns the institution, so
# both keep the full view they have everywhere else.
#
# The one exception is an allocated evaluator: evaluation work is handed to them
# deliberately, so they may see the assignment their work belongs to and the
# submissions allocated to them — and nothing else about it.


def _is_privileged(actor_role: str | None) -> bool:
    return (actor_role or "").upper() in ("ADMIN", "DEAN")


async def _has_allocation_on(
    assignment_id: UUID, actor_user_id: UUID, *, db: AsyncSession
) -> bool:
    """True when this user is allocated at least one submission of this
    assignment. Reads the M09.6 ledger; m04 keeps no copy."""
    from sqlalchemy import exists, select

    from app.modules.m09_paper_admin.assignment_models import (
        ACTIVE_STATUSES,
        EvaluationAssignment,
    )

    q = select(
        exists().where(
            EvaluationAssignment.target_entity == COURSEWORK_TARGET_ENTITY,
            EvaluationAssignment.evaluator_id == actor_user_id,
            EvaluationAssignment.status.in_(ACTIVE_STATUSES),
            EvaluationAssignment.target_id.in_(
                select(AssignmentSubmission.id).where(
                    AssignmentSubmission.assignment_id == assignment_id
                )
            ),
        )
    )
    return bool((await db.execute(q)).scalar())


class AssignmentService:

    @staticmethod
    async def assert_may_manage(
        assignment: Assignment, *, actor_user_id: UUID, actor_role: str | None
    ) -> None:
        """Only the faculty who set this coursework may change it.

        404, not 403: a faculty member has no way to know another's coursework
        exists, and saying "forbidden" would confirm that it does.
        """
        if _is_privileged(actor_role):
            return
        if assignment.created_by_user_id == actor_user_id:
            return
        raise AssignmentServiceError(
            "NOT_FOUND", "Assignment not found.", 404
        )

    @staticmethod
    async def assert_may_view(
        assignment: Assignment,
        *,
        actor_user_id: UUID,
        actor_role: str | None,
        db: AsyncSession,
    ) -> None:
        """Who may read this coursework: whoever set it, the department — or an
        evaluator it was handed to, who needs to see what their work belongs
        to."""
        if _is_privileged(actor_role) or assignment.created_by_user_id == actor_user_id:
            return
        if await _has_allocation_on(assignment.id, actor_user_id, db=db):
            return
        raise AssignmentServiceError(
            "NOT_FOUND", "Assignment not found.", 404
        )

    @staticmethod
    async def create(
        payload: AssignmentCreate, *, created_by_user_id: UUID, db: AsyncSession
    ) -> Assignment:
        _assert_questions_match_max(payload.questions, payload.max_marks)
        # Structured questions and an uploaded paper are two ways to state the same
        # thing — the questions win, so a paper is only kept when there are none.
        question_paper_url = None if payload.questions else payload.question_paper_url
        assignment = await AssignmentRepository.create(
            created_by_user_id=created_by_user_id,
            title=payload.title,
            assignment_type=payload.assignment_type,
            max_marks=payload.max_marks,
            syllabus_id=payload.syllabus_id,
            description=payload.description,
            instructions=payload.instructions,
            weightage_percent=payload.weightage_percent,
            due_date=payload.due_date,
            allow_late=payload.allow_late,
            late_penalty_percent=payload.late_penalty_percent,
            max_attempts=payload.max_attempts,
            allowed_file_types=payload.allowed_file_types,
            evaluator_user_ids=payload.evaluator_user_ids,
            questions=[q.model_dump() for q in payload.questions],
            question_paper_url=question_paper_url,
            db=db,
        )
        await db.commit()
        await db.refresh(assignment)
        return assignment

    @staticmethod
    async def get(assignment_id: UUID, *, db: AsyncSession) -> Assignment:
        return await _require_assignment(assignment_id, db=db)

    @staticmethod
    async def list_assignments(
        *,
        db: AsyncSession,
        syllabus_id: UUID | None = None,
        status: str | None = None,
        statuses: list[str] | None = None,
        created_by_user_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Assignment], int]:
        """`created_by_user_id` scopes the list to one faculty's own coursework.
        The caller decides whether to pass it — see the router, where a faculty
        always does and the department never does."""
        status_enum = AssignmentStatus(status) if status else None
        statuses_enum = [AssignmentStatus(s) for s in statuses] if statuses else None
        return await AssignmentRepository.list_assignments(
            db=db,
            syllabus_id=syllabus_id,
            status=status_enum,
            statuses=statuses_enum,
            created_by_user_id=created_by_user_id,
            offset=offset,
            limit=limit,
        )

    @staticmethod
    async def update(
        assignment_id: UUID, payload: AssignmentUpdate, *, db: AsyncSession
    ) -> Assignment:
        assignment = await _require_assignment(assignment_id, db=db)
        if assignment.status != AssignmentStatus.DRAFT:
            raise AssignmentServiceError(
                "NOT_DRAFT", "Only DRAFT assignments can be updated.", 409
            )

        fields: dict = {}
        for f in (
            "title", "description", "instructions", "assignment_type", "max_marks",
            "weightage_percent", "due_date", "allow_late", "late_penalty_percent",
            "max_attempts", "allowed_file_types",
        ):
            v = getattr(payload, f)
            if v is not None:
                fields[f] = v
        # JSONB holds no UUID type of its own — store the canonical string form.
        if payload.evaluator_user_ids is not None:
            fields["evaluator_user_ids"] = [str(e) for e in payload.evaluator_user_ids]

        # Questions / question paper. The marks must still add up, checked against
        # whichever max_marks ends up in effect — the one being set now, or the
        # existing one when the edit leaves it alone.
        if payload.questions is not None:
            effective_max = fields.get("max_marks", assignment.max_marks)
            _assert_questions_match_max(payload.questions, effective_max)
            fields["questions"] = [q.model_dump() for q in payload.questions]
            # Questions win over a paper — clear any stale paper when questions exist.
            if payload.questions:
                fields["question_paper_url"] = None
        # Only touch the paper column when the client explicitly sent it (null is a
        # meaningful "remove", so model_fields_set — not "is not None" — decides).
        if "question_paper_url" in payload.model_fields_set and "question_paper_url" not in fields:
            fields["question_paper_url"] = payload.question_paper_url

        updated = await AssignmentRepository.update(assignment_id, fields, db=db)
        await db.commit()
        await db.refresh(updated)
        return updated

    @staticmethod
    async def publish(assignment_id: UUID, *, db: AsyncSession) -> Assignment:
        assignment = await _require_assignment(assignment_id, db=db)
        if assignment.status != AssignmentStatus.DRAFT:
            raise AssignmentServiceError(
                "NOT_DRAFT", "Only DRAFT assignments can be published.", 409
            )
        if not (assignment.description or "").strip():
            raise AssignmentServiceError(
                "NO_DESCRIPTION", "A description is required before publishing.", 400
            )
        updated = await AssignmentRepository.publish(assignment_id, db=db)
        await db.commit()
        await db.refresh(updated)
        return updated

    @staticmethod
    async def close(assignment_id: UUID, *, db: AsyncSession) -> Assignment:
        assignment = await _require_assignment(assignment_id, db=db)
        if assignment.status != AssignmentStatus.PUBLISHED:
            raise AssignmentServiceError(
                "NOT_PUBLISHED", "Only PUBLISHED assignments can be closed.", 409
            )
        updated = await AssignmentRepository.close(assignment_id, db=db)
        await db.commit()
        await db.refresh(updated)
        return updated

    @staticmethod
    async def submit_for_evaluation(
        assignment_id: UUID, *, actor_user_id: UUID, db: AsyncSession
    ) -> Assignment:
        """Faculty hands a closed assignment to the department for evaluation.

        This is the gate that lets Admin/Dean allocate an Evaluator: allocation
        is refused until the faculty has finished with the assignment and said so.
        """
        assignment = await _require_assignment(assignment_id, db=db)
        if assignment.status != AssignmentStatus.CLOSED:
            raise AssignmentServiceError(
                "NOT_CLOSED",
                "Only a CLOSED assignment can be submitted for evaluation. Close "
                "the submission window first.",
                409,
            )
        updated = await AssignmentRepository.submit_for_evaluation(
            assignment_id, actor_user_id=actor_user_id, db=db
        )
        await db.commit()
        await db.refresh(updated)
        return updated

    @staticmethod
    async def finalize_marks(
        assignment_id: UUID, *, actor_user_id: UUID, db: AsyncSession
    ) -> Assignment:
        """Ratify the marks for every submission — a human decision, recorded.

        Nothing computes or infers this transition, and no AI reaches it: a person
        reviews the evaluated marks and commits to them. Once set, grading stops.
        Every submission must carry a mark first, so finalizing can never silently
        ratify an incomplete evaluation.
        """
        assignment = await _require_assignment(assignment_id, db=db)
        if assignment.status != AssignmentStatus.SUBMITTED:
            raise AssignmentServiceError(
                "NOT_UNDER_EVALUATION",
                "Only an assignment submitted for evaluation can have its marks "
                "finalized.",
                409,
            )
        ungraded = await SubmissionRepository.count_ungraded(assignment_id, db=db)
        if ungraded:
            raise AssignmentServiceError(
                "EVALUATION_INCOMPLETE",
                f"{ungraded} submission(s) are still not evaluated. Marks can only "
                f"be finalized once every submission has been evaluated.",
                409,
            )
        updated = await AssignmentRepository.finalize(
            assignment_id, actor_user_id=actor_user_id, db=db
        )
        await db.commit()
        await db.refresh(updated)
        return updated

    @staticmethod
    async def statistics(assignment_id: UUID, *, db: AsyncSession) -> dict:
        assignment = await _require_assignment(assignment_id, db=db)
        stats = await SubmissionRepository.statistics(assignment_id, db=db)
        total_students = 0
        if assignment.syllabus_id:
            total_students = await AssignmentRepository.enrolled_student_count_for_syllabus(
                assignment.syllabus_id, db=db
            )
        return {"total_students": total_students, **stats}


class SubmissionService:

    @staticmethod
    async def submit(
        assignment_id: UUID,
        student_user_id: UUID,
        *,
        content_text: str | None = None,
        content_url: str | None = None,
        tenant_id: UUID | None = None,
        db: AsyncSession,
    ) -> AssignmentSubmission:
        assignment = await _require_assignment(assignment_id, db=db)
        if assignment.status != AssignmentStatus.PUBLISHED:
            raise AssignmentServiceError(
                "NOT_PUBLISHED",
                "Submissions are only accepted for PUBLISHED assignments.",
                409,
            )

        attempts_used = await SubmissionRepository.count_student_attempts(
            assignment_id, student_user_id, db=db
        )
        if attempts_used >= assignment.max_attempts:
            raise AssignmentServiceError(
                "MAX_ATTEMPTS_REACHED",
                f"Maximum of {assignment.max_attempts} attempt(s) already used.",
                409,
            )

        if content_text is None and content_url is None:
            raise AssignmentServiceError(
                "NO_CONTENT", "Provide either content_text or content_url."
            )

        now = datetime.now(timezone.utc)
        past_due = assignment.due_date is not None and now > assignment.due_date
        if past_due and not assignment.allow_late:
            raise AssignmentServiceError(
                "DEADLINE_PASSED", "The submission deadline has passed.", 409
            )

        # Where this student sits in the rota, measured BEFORE their row exists so
        # the count does not include them. Only meaningful on a first attempt; a
        # re-attempt inherits the evaluator who read the earlier one.
        rota_index = await SubmissionRepository.count_distinct_students(
            assignment_id, db=db
        )

        submission = await SubmissionRepository.create(
            assignment_id=assignment_id,
            student_user_id=student_user_id,
            attempt_number=attempts_used + 1,
            content_text=content_text,
            content_url=content_url,
            is_late=past_due,
            db=db,
        )
        await db.commit()
        await db.refresh(submission)

        await SubmissionService._create_evaluator_work_item(
            assignment, submission, student_user_id,
            rota_index=rota_index, tenant_id=tenant_id, db=db,
        )
        return submission

    @staticmethod
    async def _create_evaluator_work_item(
        assignment: Assignment,
        submission: AssignmentSubmission,
        student_user_id: UUID,
        *,
        rota_index: int,
        tenant_id: UUID | None,
        db: AsyncSession,
    ) -> None:
        """Turn a fresh submission into evaluation work for the evaluator the
        faculty nominated.

        There is one ledger of evaluation work — the M09.6 assignment engine — and
        this goes through it exactly as a hand-made allocation does, including its
        duplicate guard and its audit trail. Nothing about who-evaluates-what is
        decided or stored here; the only thing this adds is the timing, creating
        the work item the moment the work exists rather than waiting for a human to
        repeat a decision they already made.

        An assignment with no nominees keeps the previous behaviour exactly: the
        department allocates by hand once the faculty submits.

        A failure here must never cost a student their submission — it is already
        committed, and the department can still allocate by hand — so this logs and
        returns rather than raising.
        """
        nominees = [str(e) for e in (assignment.evaluator_user_ids or [])]
        if not nominees or tenant_id is None:
            return

        from app.modules.m04_assignments.repository import COURSEWORK_TARGET_ENTITY
        from app.modules.m09_paper_admin.assignment_schemas import AssignmentCreateRequest
        from app.modules.m09_paper_admin.assignment_service import (
            AssignmentError,
            AssignmentService as EvaluationAssignmentService,
        )

        # A re-attempt is a new submission, so it needs its own work item — but it
        # goes to whoever read this student's earlier attempt, not to wherever the
        # rota now points. Only a student's first attempt takes a rota slot.
        incumbent = await AssignmentRepository.evaluator_for_student(
            assignment.id, student_user_id, db=db
        )
        evaluator_id = str(incumbent) if incumbent else nominees[rota_index % len(nominees)]
        try:
            await EvaluationAssignmentService.create_assignment(
                AssignmentCreateRequest(
                    assignment_type="REGULAR",
                    target_entity=COURSEWORK_TARGET_ENTITY,
                    target_id=submission.id,
                    evaluator_id=UUID(evaluator_id),
                    due_at=assignment.due_date,
                    notes=f"Auto-allocated from the evaluators set on “{assignment.title}”.",
                ),
                # The nomination was the faculty's decision, so the ledger records
                # them as the one who made it — not the student who triggered it.
                assigned_by=assignment.created_by_user_id,
                actor_role="FACULTY",
                tenant_id=tenant_id,
                db=db,
            )
            # Same notification a hand-made allocation sends — the work item is the
            # same, so the evaluator hears about it the same way.
            from app.core.notifications.dispatch import notify_user
            from app.core.notifications.models import NotificationType

            await notify_user(
                db,
                notification_type=NotificationType.REVIEW_REQUESTED,
                recipient_user_id=UUID(evaluator_id),
                title=f"Evaluation assigned: {assignment.title}",
                body="A coursework submission has been allocated to you for evaluation.",
                entity_type="AssignmentSubmission",
                entity_id=str(submission.id),
            )
        except AssignmentError as exc:
            # DUPLICATE_ACTIVE_ASSIGNMENT is expected if a human already allocated
            # this submission; their decision wins.
            logger.info(
                "coursework auto-allocation skipped for submission %s: %s",
                submission.id, exc,
            )
        except Exception:
            logger.exception(
                "coursework auto-allocation failed for submission %s; the "
                "department can still allocate it by hand",
                submission.id,
            )

    @staticmethod
    async def get_submission(submission_id: UUID, *, db: AsyncSession) -> AssignmentSubmission:
        return await _require_submission(submission_id, db=db)

    @staticmethod
    async def list_for_assignment(
        assignment_id: UUID,
        *,
        actor_user_id: UUID,
        actor_role: str | None,
        db: AsyncSession,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[AssignmentSubmission], int]:
        """The submissions the caller is entitled to see.

        Whoever set the coursework — and the department — see every submission.
        An evaluator sees ONLY the submissions allocated to them: the work was
        handed to them one submission at a time, and the rest of the class is not
        theirs to read.
        """
        assignment = await _require_assignment(assignment_id, db=db)
        if (
            _is_privileged(actor_role)
            or assignment.created_by_user_id == actor_user_id
        ):
            return await SubmissionRepository.list_for_assignment(
                assignment_id, db=db, offset=offset, limit=limit
            )

        if await _has_allocation_on(assignment_id, actor_user_id, db=db):
            return await SubmissionRepository.list_allocated_to(
                assignment_id, actor_user_id, db=db, offset=offset, limit=limit
            )

        raise AssignmentServiceError("NOT_FOUND", "Assignment not found.", 404)

    @staticmethod
    async def list_for_student(
        student_user_id: UUID,
        *,
        db: AsyncSession,
        syllabus_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AssignmentSubmission], int]:
        return await SubmissionRepository.list_for_student(
            student_user_id, db=db, syllabus_id=syllabus_id, offset=offset, limit=limit
        )

    @staticmethod
    async def _assert_may_evaluate(
        sub: AssignmentSubmission,
        assignment: Assignment,
        *,
        actor_user_id: UUID,
        actor_role: str | None,
        db: AsyncSession,
    ) -> None:
        """Once an assignment is out for evaluation, only its allocated evaluator
        may mark a submission.

        Allocation lives in the M09.6 assignment engine, so this reads that ledger
        rather than keeping a second copy of who-evaluates-what. Before the
        department takes over (status < SUBMITTED) the OWNING faculty still grades
        as they always have, so earlier coursework is untouched.
        """
        if assignment.status != AssignmentStatus.SUBMITTED:
            # Not out for evaluation yet — the faculty who set it grades it. Any
            # other faculty is a peer with no claim on this coursework at all.
            if _is_privileged(actor_role) or assignment.created_by_user_id == actor_user_id:
                return
            raise AssignmentServiceError(
                "NOT_FOUND", "Submission not found.", 404
            )
        if (actor_role or "").upper() == "ADMIN":
            return

        allocation = await AssignmentRepository.active_evaluator_for_submission(
            sub.id, db=db
        )
        if allocation is None:
            raise AssignmentServiceError(
                "NO_EVALUATOR_ASSIGNED",
                "This submission is awaiting evaluator allocation. The department "
                "must assign an evaluator before it can be evaluated.",
                409,
            )
        if allocation != actor_user_id:
            raise AssignmentServiceError(
                "NOT_ASSIGNED_EVALUATOR",
                "This submission is allocated to a different evaluator.",
                403,
            )

    @staticmethod
    async def grade(
        submission_id: UUID,
        *,
        marks_obtained: float,
        feedback: str | None,
        graded_by_user_id: UUID,
        actor_role: str | None = None,
        db: AsyncSession,
    ) -> tuple[AssignmentSubmission, float | None]:
        sub = await _require_submission(submission_id, db=db)
        assignment = await _require_assignment(sub.assignment_id, db=db)
        if marks_obtained > float(assignment.max_marks):
            raise AssignmentServiceError(
                "MARKS_EXCEED_MAX",
                f"marks_obtained cannot exceed max_marks ({assignment.max_marks}).",
            )
        if assignment.status == AssignmentStatus.FINALIZED:
            raise AssignmentServiceError(
                "MARKS_FINALIZED",
                "The marks for this assignment have been finalized and can no "
                "longer be changed.",
                409,
            )
        await SubmissionService._assert_may_evaluate(
            sub, assignment, actor_user_id=graded_by_user_id, actor_role=actor_role, db=db
        )
        previous_marks_obtained = sub.marks_obtained
        updated = await SubmissionRepository.grade(
            submission_id,
            marks_obtained=marks_obtained,
            feedback=feedback,
            graded_by_user_id=graded_by_user_id,
            db=db,
        )
        await db.commit()
        await db.refresh(updated)
        return updated, previous_marks_obtained

    @staticmethod
    async def mark_returned(submission_id: UUID, *, db: AsyncSession) -> AssignmentSubmission:
        sub = await _require_submission(submission_id, db=db)
        if sub.status != "GRADED":
            raise AssignmentServiceError(
                "NOT_GRADED", "Submission must be GRADED before it can be returned.", 409
            )
        updated = await SubmissionRepository.mark_returned(submission_id, db=db)
        await db.commit()
        await db.refresh(updated)
        return updated
