"""
M06 Labs & Assignment Evaluator — Service layer.

Architecture contract:
  - All business logic lives here; router is pure HTTP glue.
  - LabServiceError carries code, message, status_code for HTTP translation.
  - Evaluation Celery tasks dispatched via TaskJobPublicRepository.
  - Grade ledger written ONLY via ratify(); never by any Celery task.
  - AI advises, humans decide: rubric scores are suggestions until ratified.
  - Audit logging on every state-changing action.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m06_labs_evaluator.models import (
    AssignmentStatus,
    LabAssignment,
    LabEvaluation,
    LabSubmission,
    GradeLedger,
    SubmissionStatus,
    SubmissionType,
)
from app.modules.m06_labs_evaluator.repository import (
    AssignmentRepository,
    EvaluationRepository,
    GradeLedgerRepository,
    SubmissionRepository,
    TaskJobPublicRepository,
)
from app.modules.m06_labs_evaluator.schemas import (
    AssignmentCreate,
    AssignmentUpdate,
    CriterionScoreUpdate,
)

logger = logging.getLogger("vidya.service.m06")


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------

class LabServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Internal guards
# ---------------------------------------------------------------------------

async def _require_assignment(
    assignment_id: UUID,
    *,
    db: AsyncSession,
) -> LabAssignment:
    obj = await AssignmentRepository.get_by_id(assignment_id, db=db)
    if obj is None:
        raise LabServiceError("NOT_FOUND", "Assignment not found.", 404)
    return obj


async def _require_submission(
    submission_id: UUID,
    *,
    db: AsyncSession,
    load_evaluation: bool = False,
) -> LabSubmission:
    obj = await SubmissionRepository.get_by_id(
        submission_id, db=db, load_evaluation=load_evaluation
    )
    if obj is None:
        raise LabServiceError("NOT_FOUND", "Submission not found.", 404)
    return obj


def _compute_max_marks(rubric: list[dict]) -> int:
    return sum(int(c.get("max_marks", 0)) for c in rubric)


def _validate_rubric_weights(rubric: list[dict]) -> None:
    if not rubric:
        return
    total = sum(float(c.get("weight", 0)) for c in rubric)
    if abs(total - 1.0) > 0.01:
        raise LabServiceError(
            "INVALID_RUBRIC",
            f"Rubric criterion weights must sum to 1.0; got {total:.3f}.",
        )


# ---------------------------------------------------------------------------
# AssignmentService
# ---------------------------------------------------------------------------

class AssignmentService:

    @staticmethod
    async def create(
        payload: AssignmentCreate,
        *,
        created_by_user_id: UUID,
        db: AsyncSession,
    ) -> LabAssignment:
        rubric_dicts = [c.model_dump() for c in payload.rubric]
        tc_dicts     = [t.model_dump() for t in payload.test_cases]
        _validate_rubric_weights(rubric_dicts)

        if payload.submission_type == "CODE" and not payload.language:
            raise LabServiceError(
                "LANGUAGE_REQUIRED",
                "language is required for CODE assignments.",
            )

        assignment = await AssignmentRepository.create(
            created_by_user_id=created_by_user_id,
            title=payload.title,
            submission_type=SubmissionType(payload.submission_type),
            rubric=rubric_dicts,
            syllabus_id=payload.syllabus_id,
            kit_assignment_id=payload.kit_assignment_id,
            description=payload.description,
            instructions=payload.instructions,
            language=payload.language,
            test_cases=tc_dicts,
            deadline=payload.deadline,
            ai_not_permitted=payload.ai_not_permitted,
            allow_late=payload.allow_late,
            plagiarism_threshold=float(payload.plagiarism_threshold),
            lab_group=payload.lab_group,
            program_number=payload.program_number,
            db=db,
        )
        await db.commit()
        await db.refresh(assignment)
        return assignment

    @staticmethod
    async def get(
        assignment_id: UUID,
        *,
        db: AsyncSession,
    ) -> LabAssignment:
        return await _require_assignment(assignment_id, db=db)

    @staticmethod
    async def list_assignments(
        *,
        db: AsyncSession,
        syllabus_id: UUID | None = None,
        status: str | None = None,
        created_by_user_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[LabAssignment], int]:
        status_enum = AssignmentStatus(status) if status else None
        return await AssignmentRepository.list_assignments(
            db=db,
            syllabus_id=syllabus_id,
            status=status_enum,
            created_by_user_id=created_by_user_id,
            offset=offset,
            limit=limit,
        )

    @staticmethod
    async def update(
        assignment_id: UUID,
        payload: AssignmentUpdate,
        *,
        db: AsyncSession,
    ) -> LabAssignment:
        assignment = await _require_assignment(assignment_id, db=db)
        if assignment.status != AssignmentStatus.DRAFT:
            raise LabServiceError(
                "NOT_DRAFT",
                "Only DRAFT assignments can be updated.",
                409,
            )

        fields: dict = {}
        if payload.title is not None:
            fields["title"] = payload.title
        if payload.description is not None:
            fields["description"] = payload.description
        if payload.instructions is not None:
            fields["instructions"] = payload.instructions
        if payload.rubric is not None:
            rubric_dicts = [c.model_dump() for c in payload.rubric]
            _validate_rubric_weights(rubric_dicts)
            fields["rubric"] = rubric_dicts
        if payload.test_cases is not None:
            fields["test_cases"] = [t.model_dump() for t in payload.test_cases]
        if payload.deadline is not None:
            fields["deadline"] = payload.deadline
        if payload.ai_not_permitted is not None:
            fields["ai_not_permitted"] = payload.ai_not_permitted
        if payload.allow_late is not None:
            fields["allow_late"] = payload.allow_late
        if payload.plagiarism_threshold is not None:
            fields["plagiarism_threshold"] = payload.plagiarism_threshold
        if payload.language is not None:
            fields["language"] = payload.language
        if payload.lab_group is not None:
            fields["lab_group"] = payload.lab_group
        if payload.program_number is not None:
            fields["program_number"] = payload.program_number

        updated = await AssignmentRepository.update(assignment_id, fields, db=db)
        await db.commit()
        await db.refresh(updated)
        return updated

    @staticmethod
    async def publish(
        assignment_id: UUID,
        *,
        db: AsyncSession,
    ) -> LabAssignment:
        assignment = await _require_assignment(assignment_id, db=db)
        if assignment.status != AssignmentStatus.DRAFT:
            raise LabServiceError(
                "NOT_DRAFT",
                "Only DRAFT assignments can be published.",
                409,
            )
        if not (assignment.description or "").strip():
            raise LabServiceError(
                "NO_PROBLEM_STATEMENT",
                "A problem statement is required before publishing.",
            )
        if not assignment.rubric:
            raise LabServiceError(
                "NO_RUBRIC",
                "Assignment must have at least one rubric criterion before publishing.",
            )

        max_marks = _compute_max_marks(assignment.rubric)
        updated = await AssignmentRepository.publish(assignment_id, max_marks, db=db)
        await db.commit()
        await db.refresh(updated)
        return updated

    @staticmethod
    async def close(
        assignment_id: UUID,
        *,
        db: AsyncSession,
    ) -> LabAssignment:
        assignment = await _require_assignment(assignment_id, db=db)
        if assignment.status != AssignmentStatus.PUBLISHED:
            raise LabServiceError(
                "NOT_PUBLISHED",
                "Only PUBLISHED assignments can be closed.",
                409,
            )
        updated = await AssignmentRepository.close(assignment_id, db=db)
        await db.commit()
        await db.refresh(updated)
        return updated


# ---------------------------------------------------------------------------
# SubmissionService
# ---------------------------------------------------------------------------

class SubmissionService:

    @staticmethod
    async def submit(
        assignment_id: UUID,
        student_user_id: UUID,
        *,
        content_text: str | None = None,
        content_url: str | None = None,
        github_url: str | None = None,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> tuple[LabSubmission, UUID]:
        """
        Create a submission and dispatch the evaluation Celery task.
        Returns (submission, job_id).
        """
        assignment = await _require_assignment(assignment_id, db=db)
        if assignment.status != AssignmentStatus.PUBLISHED:
            raise LabServiceError(
                "NOT_PUBLISHED",
                "Submissions are only accepted for PUBLISHED assignments.",
                409,
            )

        # One submission per student per assignment
        existing = await SubmissionRepository.get_student_submission(
            assignment_id, student_user_id, db=db
        )
        if existing is not None:
            raise LabServiceError(
                "ALREADY_SUBMITTED",
                "You have already submitted for this assignment.",
                409,
            )

        if content_text is None and content_url is None and github_url is None:
            raise LabServiceError(
                "NO_CONTENT",
                "Provide at least one of content_text, content_url, or github_url.",
            )

        now = datetime.now(timezone.utc)
        is_late = (
            assignment.deadline is not None
            and now > assignment.deadline
            and not assignment.allow_late
        )
        if is_late and not assignment.allow_late:
            raise LabServiceError(
                "DEADLINE_PASSED",
                "The submission deadline has passed.",
                409,
            )

        submission = await SubmissionRepository.create(
            assignment_id=assignment_id,
            student_user_id=student_user_id,
            submission_type=assignment.submission_type,
            content_text=content_text,
            content_url=content_url,
            github_url=github_url,
            is_late=assignment.deadline is not None and now > assignment.deadline,
            db=db,
        )

        # Create task_jobs row and dispatch evaluation task atomically
        job_id = await TaskJobPublicRepository.create(
            tenant_id=tenant_id,
            task_type="evaluate_lab_submission",
            queue_name="heavy",
            payload={
                "submission_id": str(submission.id),
                "assignment_id": str(assignment_id),
                "schema_name":   schema_name,
            },
            db=db,
        )
        await SubmissionRepository.set_eval_job(submission.id, job_id, db=db)
        await db.commit()
        await db.refresh(submission)

        # Dispatch Celery task after commit (idempotent: task reads submission by id)
        from app.workers.heavy.evaluate_lab_submission import evaluate_lab_submission
        evaluate_lab_submission.apply_async(
            kwargs={
                "job_id":        str(job_id),
                "submission_id": str(submission.id),
                "assignment_id": str(assignment_id),
                "schema_name":   schema_name,
            }
        )
        logger.info("Evaluation job %s dispatched for submission %s", job_id, submission.id)
        return submission, job_id

    @staticmethod
    async def get_submission(
        submission_id: UUID,
        *,
        db: AsyncSession,
        load_evaluation: bool = False,
    ) -> LabSubmission:
        return await _require_submission(
            submission_id, db=db, load_evaluation=load_evaluation
        )

    @staticmethod
    async def list_for_assignment(
        assignment_id: UUID,
        *,
        db: AsyncSession,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[LabSubmission], int]:
        await _require_assignment(assignment_id, db=db)
        return await SubmissionRepository.list_for_assignment(
            assignment_id, db=db, offset=offset, limit=limit
        )

    @staticmethod
    async def list_for_student(
        student_user_id: UUID,
        *,
        db: AsyncSession,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[LabSubmission], int]:
        return await SubmissionRepository.list_for_student(
            student_user_id, db=db, offset=offset, limit=limit
        )


# ---------------------------------------------------------------------------
# ReviewService — faculty review panel actions
# ---------------------------------------------------------------------------

class ReviewService:

    @staticmethod
    async def get_review_panel(
        submission_id: UUID,
        *,
        db: AsyncSession,
    ) -> tuple[LabSubmission, LabAssignment, GradeLedger | None]:
        sub = await _require_submission(submission_id, db=db, load_evaluation=True)
        assignment = await _require_assignment(sub.assignment_id, db=db)
        grade_entry = await GradeLedgerRepository.get_by_submission(submission_id, db=db)

        # Mark as REVIEWED so the faculty panel is tracked
        if sub.status == SubmissionStatus.EVALUATED:
            await SubmissionRepository.set_status(
                submission_id, SubmissionStatus.REVIEWED, db=db
            )
            await db.commit()
            await db.refresh(sub)

        return sub, assignment, grade_entry

    @staticmethod
    async def update_scores(
        submission_id: UUID,
        score_updates: list[CriterionScoreUpdate],
        *,
        db: AsyncSession,
    ) -> LabEvaluation:
        sub = await _require_submission(submission_id, db=db, load_evaluation=True)
        if sub.status not in (SubmissionStatus.EVALUATED, SubmissionStatus.REVIEWED):
            raise LabServiceError(
                "NOT_EVALUATED",
                "Submission must be EVALUATED before scores can be edited.",
                409,
            )

        evaluation = await EvaluationRepository.get_by_submission(submission_id, db=db)
        if evaluation is None:
            raise LabServiceError("NO_EVALUATION", "No AI evaluation found.", 404)

        # Merge human overrides into rubric_scores
        update_map = {u.criterion_id: u for u in score_updates}
        updated_scores = []
        for criterion in evaluation.rubric_scores:
            cid = criterion.get("criterion_id", "")
            if cid in update_map:
                u = update_map[cid]
                criterion = dict(criterion)
                criterion["human_score"] = u.human_score
                criterion["human_note"]  = u.human_note
            updated_scores.append(criterion)

        # Compute weighted human total from updated_scores
        assignment = await _require_assignment(sub.assignment_id, db=db)
        overall = _compute_overall_human_score(updated_scores, assignment.rubric)

        await EvaluationRepository.update_scores(
            evaluation.id, updated_scores, overall, db=db
        )
        await db.commit()
        await db.refresh(evaluation)
        return evaluation

    @staticmethod
    async def ratify(
        submission_id: UUID,
        ratified_by_user_id: UUID,
        *,
        ratification_note: str | None = None,
        db: AsyncSession,
    ) -> GradeLedger:
        """
        Write to grade_ledger. Called ONLY by the ratify endpoint.
        Celery tasks must never call this.
        """
        sub = await _require_submission(submission_id, db=db, load_evaluation=True)
        if sub.status == SubmissionStatus.RATIFIED:
            raise LabServiceError("ALREADY_RATIFIED", "Already ratified.", 409)
        if sub.status not in (SubmissionStatus.EVALUATED, SubmissionStatus.REVIEWED):
            raise LabServiceError(
                "NOT_READY",
                "Submission must be EVALUATED before ratification.",
                409,
            )

        existing = await GradeLedgerRepository.get_by_submission(submission_id, db=db)
        if existing is not None:
            raise LabServiceError("ALREADY_RATIFIED", "Grade already recorded.", 409)

        evaluation = await EvaluationRepository.get_by_submission(submission_id, db=db)
        if evaluation is None:
            raise LabServiceError("NO_EVALUATION", "No AI evaluation found.", 404)

        assignment = await _require_assignment(sub.assignment_id, db=db)

        # Use human score if set, else fall back to AI score
        final_score = (
            float(evaluation.overall_human_score)
            if evaluation.overall_human_score is not None
            else float(evaluation.overall_ai_score or 0)
        )

        grade = await GradeLedgerRepository.create(
            submission_id=submission_id,
            assignment_id=sub.assignment_id,
            student_user_id=sub.student_user_id,
            ratified_by_user_id=ratified_by_user_id,
            final_score=final_score,
            max_marks=assignment.max_marks or 0,
            ratification_note=ratification_note,
            db=db,
        )
        await SubmissionRepository.set_status(submission_id, SubmissionStatus.RATIFIED, db=db)
        await db.commit()
        await db.refresh(grade)
        return grade

    @staticmethod
    async def get_grade(
        submission_id: UUID,
        *,
        db: AsyncSession,
    ) -> GradeLedger | None:
        return await GradeLedgerRepository.get_by_submission(submission_id, db=db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_overall_human_score(rubric_scores: list[dict], rubric_def: list[dict]) -> float:
    """Weighted sum of human scores across criteria."""
    weight_map = {c.get("criterion_id"): float(c.get("weight", 0)) for c in rubric_def}
    total = 0.0
    for row in rubric_scores:
        cid   = row.get("criterion_id", "")
        score = row.get("human_score") or row.get("ai_score") or 0
        weight = weight_map.get(cid, 0)
        max_m  = float(next(
            (c.get("max_marks", 0) for c in rubric_def if c.get("criterion_id") == cid), 0
        ))
        total += float(score) * weight
    return round(total, 2)
