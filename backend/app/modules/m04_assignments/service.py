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
from app.modules.m04_assignments.repository import AssignmentRepository, SubmissionRepository
from app.modules.m04_assignments.schemas import AssignmentCreate, AssignmentUpdate

logger = logging.getLogger("vidya.service.m04")


class AssignmentServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


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


class AssignmentService:

    @staticmethod
    async def create(
        payload: AssignmentCreate, *, created_by_user_id: UUID, db: AsyncSession
    ) -> Assignment:
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
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Assignment], int]:
        status_enum = AssignmentStatus(status) if status else None
        statuses_enum = [AssignmentStatus(s) for s in statuses] if statuses else None
        return await AssignmentRepository.list_assignments(
            db=db,
            syllabus_id=syllabus_id,
            status=status_enum,
            statuses=statuses_enum,
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
        return submission

    @staticmethod
    async def get_submission(submission_id: UUID, *, db: AsyncSession) -> AssignmentSubmission:
        return await _require_submission(submission_id, db=db)

    @staticmethod
    async def list_for_assignment(
        assignment_id: UUID, *, db: AsyncSession, offset: int = 0, limit: int = 100
    ) -> tuple[list[AssignmentSubmission], int]:
        await _require_assignment(assignment_id, db=db)
        return await SubmissionRepository.list_for_assignment(
            assignment_id, db=db, offset=offset, limit=limit
        )

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
    async def grade(
        submission_id: UUID,
        *,
        marks_obtained: float,
        feedback: str | None,
        graded_by_user_id: UUID,
        db: AsyncSession,
    ) -> AssignmentSubmission:
        sub = await _require_submission(submission_id, db=db)
        assignment = await _require_assignment(sub.assignment_id, db=db)
        if marks_obtained > float(assignment.max_marks):
            raise AssignmentServiceError(
                "MARKS_EXCEED_MAX",
                f"marks_obtained cannot exceed max_marks ({assignment.max_marks}).",
            )
        updated = await SubmissionRepository.grade(
            submission_id,
            marks_obtained=marks_obtained,
            feedback=feedback,
            graded_by_user_id=graded_by_user_id,
            db=db,
        )
        await db.commit()
        await db.refresh(updated)
        return updated

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
