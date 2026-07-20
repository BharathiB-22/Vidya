"""
M04 Assignments — Repository layer.

Conventions (mirrors M06):
  - All methods are @staticmethod with keyword-only `db: AsyncSession`.
  - Write methods use db.flush() so callers control commit boundaries.
  - No cross-tenant queries; search_path set at connection time.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m04_assignments.models import (
    Assignment,
    AssignmentStatus,
    AssignmentSubmission,
    SubmissionStatus,
)

# How coursework identifies itself to the M09.6 assignment engine, whose target is
# polymorphic (scanned_script, revaluation_request, …). One student submission is
# one unit of evaluation work.
COURSEWORK_TARGET_ENTITY = "assignment_submission"


class AssignmentRepository:

    @staticmethod
    async def create(
        *,
        created_by_user_id: UUID,
        title: str,
        assignment_type: str,
        max_marks: float,
        syllabus_id: UUID | None = None,
        description: str | None = None,
        instructions: str | None = None,
        weightage_percent: float | None = None,
        due_date: datetime | None = None,
        allow_late: bool = True,
        late_penalty_percent: float | None = None,
        max_attempts: int = 1,
        allowed_file_types: list[str] | None = None,
        evaluator_user_ids: list[UUID] | None = None,
        questions: list[dict] | None = None,
        question_paper_url: str | None = None,
        db: AsyncSession,
    ) -> Assignment:
        obj = Assignment(
            created_by_user_id=created_by_user_id,
            title=title,
            assignment_type=assignment_type,
            max_marks=max_marks,
            syllabus_id=syllabus_id,
            description=description,
            instructions=instructions,
            weightage_percent=weightage_percent,
            due_date=due_date,
            allow_late=allow_late,
            late_penalty_percent=late_penalty_percent,
            max_attempts=max_attempts,
            allowed_file_types=allowed_file_types or [],
            # JSONB holds no UUID type of its own — store the canonical string form.
            evaluator_user_ids=[str(e) for e in (evaluator_user_ids or [])],
            questions=questions or [],
            question_paper_url=question_paper_url,
            status=AssignmentStatus.DRAFT,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def get_by_id(assignment_id: UUID, *, db: AsyncSession) -> Assignment | None:
        result = await db.execute(select(Assignment).where(Assignment.id == assignment_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_assignments(
        *,
        db: AsyncSession,
        syllabus_id: UUID | None = None,
        status: AssignmentStatus | None = None,
        statuses: list[AssignmentStatus] | None = None,
        created_by_user_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Assignment], int]:
        filters: list[Any] = []
        if syllabus_id:
            filters.append(Assignment.syllabus_id == syllabus_id)
        if status:
            filters.append(Assignment.status == status)
        if statuses:
            filters.append(Assignment.status.in_(statuses))
        if created_by_user_id:
            filters.append(Assignment.created_by_user_id == created_by_user_id)

        count_q = select(func.count()).select_from(Assignment)
        list_q = select(Assignment).order_by(Assignment.created_at.desc())
        for f in filters:
            count_q = count_q.where(f)
            list_q = list_q.where(f)
        list_q = list_q.offset(offset).limit(limit)

        total = (await db.execute(count_q)).scalar_one()
        items = (await db.execute(list_q)).scalars().all()
        return list(items), total

    @staticmethod
    async def update(assignment_id: UUID, fields: dict, *, db: AsyncSession) -> Assignment | None:
        obj = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if obj is None:
            return None
        for k, v in fields.items():
            setattr(obj, k, v)
        obj.updated_at = datetime.utcnow()
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def publish(assignment_id: UUID, *, db: AsyncSession) -> Assignment | None:
        obj = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if obj is None:
            return None
        obj.status = AssignmentStatus.PUBLISHED
        obj.published_at = datetime.utcnow()
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def close(assignment_id: UUID, *, db: AsyncSession) -> Assignment | None:
        obj = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if obj is None:
            return None
        obj.status = AssignmentStatus.CLOSED
        obj.closed_at = datetime.utcnow()
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def active_evaluator_for_submission(
        submission_id: UUID, *, db: AsyncSession
    ) -> UUID | None:
        """Who the M09.6 assignment engine currently has evaluating this submission.

        Evaluator allocation is not duplicated into m04 — that engine is the one
        ledger for evaluation work, so this reads it. Returns None when nothing is
        allocated yet. Reassignment leaves the superseded row in a non-active
        status, so at most one row can match.
        """
        from app.modules.m09_paper_admin.assignment_models import (
            ACTIVE_STATUSES,
            EvaluationAssignment,
        )
        result = await db.execute(
            select(EvaluationAssignment.evaluator_id).where(
                EvaluationAssignment.target_entity == COURSEWORK_TARGET_ENTITY,
                EvaluationAssignment.target_id == submission_id,
                EvaluationAssignment.status.in_(ACTIVE_STATUSES),
            )
        )
        return result.scalars().first()

    @staticmethod
    async def evaluator_for_student(
        assignment_id: UUID, student_user_id: UUID, *, db: AsyncSession
    ) -> UUID | None:
        """Who is already evaluating this student's work on this assignment.

        A re-attempt is a new submission and so a new unit of work, but it is the
        same student's answer to the same question — it belongs with whoever read
        the first one, not with whoever the rota happens to point at now. Reads the
        M09.6 ledger; m04 keeps no copy.
        """
        from app.modules.m09_paper_admin.assignment_models import EvaluationAssignment

        result = await db.execute(
            select(EvaluationAssignment.evaluator_id)
            .join(
                AssignmentSubmission,
                AssignmentSubmission.id == EvaluationAssignment.target_id,
            )
            .where(
                EvaluationAssignment.target_entity == COURSEWORK_TARGET_ENTITY,
                AssignmentSubmission.assignment_id == assignment_id,
                AssignmentSubmission.student_user_id == student_user_id,
            )
            .order_by(EvaluationAssignment.assigned_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    @staticmethod
    async def submit_for_evaluation(
        assignment_id: UUID, *, actor_user_id: UUID, db: AsyncSession
    ) -> Assignment | None:
        obj = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if obj is None:
            return None
        obj.status = AssignmentStatus.SUBMITTED
        obj.submitted_at = datetime.utcnow()
        obj.submitted_by_user_id = actor_user_id
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def finalize(
        assignment_id: UUID, *, actor_user_id: UUID, db: AsyncSession
    ) -> Assignment | None:
        obj = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if obj is None:
            return None
        obj.status = AssignmentStatus.FINALIZED
        obj.finalized_at = datetime.utcnow()
        obj.finalized_by_user_id = actor_user_id
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def enrolled_section_ids_for_syllabus(
        syllabus_id: UUID, *, db: AsyncSession
    ) -> list[UUID]:
        """Resolve section_ids whose students are enrolled in this syllabus's course.

        Join: syllabi -> course_id -> subject_assignments (active) -> section_id.
        """
        rows = (
            await db.execute(
                text(
                    "SELECT DISTINCT sa.section_id "
                    "FROM syllabi s "
                    "JOIN subject_assignments sa ON sa.course_id = s.course_id "
                    "WHERE s.id = :sid AND sa.is_active = true AND sa.section_id IS NOT NULL"
                ),
                {"sid": str(syllabus_id)},
            )
        ).fetchall()
        return [r[0] for r in rows]

    @staticmethod
    async def enrolled_student_count_for_syllabus(
        syllabus_id: UUID, *, db: AsyncSession
    ) -> int:
        row = (
            await db.execute(
                text(
                    "SELECT COUNT(DISTINCT ae.student_id) "
                    "FROM syllabi s "
                    "JOIN subject_assignments sa ON sa.course_id = s.course_id "
                    "JOIN acad_enrollments ae ON ae.section_id = sa.section_id AND ae.is_active = true "
                    "WHERE s.id = :sid AND sa.is_active = true"
                ),
                {"sid": str(syllabus_id)},
            )
        ).one_or_none()
        return int(row[0]) if row else 0


class SubmissionRepository:

    @staticmethod
    async def create(
        *,
        assignment_id: UUID,
        student_user_id: UUID,
        attempt_number: int,
        content_text: str | None,
        content_url: str | None,
        is_late: bool,
        db: AsyncSession,
    ) -> AssignmentSubmission:
        obj = AssignmentSubmission(
            assignment_id=assignment_id,
            student_user_id=student_user_id,
            attempt_number=attempt_number,
            content_text=content_text,
            content_url=content_url,
            is_late=is_late,
            status=SubmissionStatus.SUBMITTED,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def get_by_id(submission_id: UUID, *, db: AsyncSession) -> AssignmentSubmission | None:
        result = await db.execute(
            select(AssignmentSubmission).where(AssignmentSubmission.id == submission_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def count_student_attempts(
        assignment_id: UUID, student_user_id: UUID, *, db: AsyncSession
    ) -> int:
        result = await db.execute(
            select(func.count()).select_from(AssignmentSubmission).where(
                AssignmentSubmission.assignment_id == assignment_id,
                AssignmentSubmission.student_user_id == student_user_id,
            )
        )
        return result.scalar_one()

    @staticmethod
    async def count_distinct_students(
        assignment_id: UUID, *, db: AsyncSession
    ) -> int:
        """How many students have submitted anything at all.

        This is a student's position in the evaluator rota. It counts STUDENTS,
        not submissions, so a re-attempt cannot shift the rota by one — and a
        re-attempt does not consult it anyway (see `evaluator_for_student`).
        """
        result = await db.execute(
            select(func.count(func.distinct(AssignmentSubmission.student_user_id)))
            .where(AssignmentSubmission.assignment_id == assignment_id)
        )
        return result.scalar_one()

    @staticmethod
    async def list_for_assignment(
        assignment_id: UUID, *, db: AsyncSession, offset: int = 0, limit: int = 100
    ) -> tuple[list[AssignmentSubmission], int]:
        count_q = select(func.count()).select_from(AssignmentSubmission).where(
            AssignmentSubmission.assignment_id == assignment_id
        )
        list_q = (
            select(AssignmentSubmission)
            .where(AssignmentSubmission.assignment_id == assignment_id)
            .order_by(AssignmentSubmission.submitted_at.desc())
            .offset(offset)
            .limit(limit)
        )
        total = (await db.execute(count_q)).scalar_one()
        items = (await db.execute(list_q)).scalars().all()
        return list(items), total

    @staticmethod
    async def list_allocated_to(
        assignment_id: UUID,
        evaluator_id: UUID,
        *,
        db: AsyncSession,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[AssignmentSubmission], int]:
        """This assignment's submissions that are allocated to one evaluator.

        Scopes an evaluator to the work actually handed to them. Reads the M09.6
        ledger rather than any copy of it.
        """
        from app.modules.m09_paper_admin.assignment_models import (
            ACTIVE_STATUSES,
            EvaluationAssignment,
        )

        allocated = select(EvaluationAssignment.target_id).where(
            EvaluationAssignment.target_entity == COURSEWORK_TARGET_ENTITY,
            EvaluationAssignment.evaluator_id == evaluator_id,
            EvaluationAssignment.status.in_(ACTIVE_STATUSES),
        )
        where = (
            AssignmentSubmission.assignment_id == assignment_id,
            AssignmentSubmission.id.in_(allocated),
        )
        count_q = select(func.count()).select_from(AssignmentSubmission).where(*where)
        list_q = (
            select(AssignmentSubmission)
            .where(*where)
            .order_by(AssignmentSubmission.submitted_at.desc())
            .offset(offset)
            .limit(limit)
        )
        total = (await db.execute(count_q)).scalar_one()
        items = (await db.execute(list_q)).scalars().all()
        return list(items), total

    @staticmethod
    async def list_for_student(
        student_user_id: UUID,
        *,
        db: AsyncSession,
        syllabus_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AssignmentSubmission], int]:
        q = select(AssignmentSubmission).where(
            AssignmentSubmission.student_user_id == student_user_id
        )
        count_q = select(func.count()).select_from(AssignmentSubmission).where(
            AssignmentSubmission.student_user_id == student_user_id
        )
        if syllabus_id:
            q = q.join(Assignment, Assignment.id == AssignmentSubmission.assignment_id).where(
                Assignment.syllabus_id == syllabus_id
            )
            count_q = count_q.join(
                Assignment, Assignment.id == AssignmentSubmission.assignment_id
            ).where(Assignment.syllabus_id == syllabus_id)
        q = q.order_by(AssignmentSubmission.submitted_at.desc()).offset(offset).limit(limit)

        total = (await db.execute(count_q)).scalar_one()
        items = (await db.execute(q)).scalars().all()
        return list(items), total

    @staticmethod
    async def grade(
        submission_id: UUID,
        *,
        marks_obtained: float,
        feedback: str | None,
        graded_by_user_id: UUID,
        db: AsyncSession,
    ) -> AssignmentSubmission | None:
        obj = await SubmissionRepository.get_by_id(submission_id, db=db)
        if obj is None:
            return None
        obj.marks_obtained = marks_obtained
        obj.feedback = feedback
        obj.graded_by_user_id = graded_by_user_id
        obj.graded_at = datetime.utcnow()
        obj.status = SubmissionStatus.GRADED
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def mark_returned(submission_id: UUID, *, db: AsyncSession) -> AssignmentSubmission | None:
        obj = await SubmissionRepository.get_by_id(submission_id, db=db)
        if obj is None:
            return None
        obj.status = SubmissionStatus.RETURNED
        obj.returned_at = datetime.utcnow()
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def count_ungraded(assignment_id: UUID, *, db: AsyncSession) -> int:
        """Submissions still carrying no mark. Guards mark finalization."""
        result = await db.execute(
            select(func.count())
            .select_from(AssignmentSubmission)
            .where(
                AssignmentSubmission.assignment_id == assignment_id,
                AssignmentSubmission.marks_obtained.is_(None),
            )
        )
        return int(result.scalar() or 0)

    @staticmethod
    async def statistics(assignment_id: UUID, *, db: AsyncSession) -> dict:
        rows = (
            await db.execute(
                select(AssignmentSubmission).where(
                    AssignmentSubmission.assignment_id == assignment_id
                )
            )
        ).scalars().all()
        submitted = len(rows)
        graded = [r for r in rows if r.marks_obtained is not None]
        late = sum(1 for r in rows if r.is_late)
        avg = (
            sum(float(r.marks_obtained) for r in graded) / len(graded)
            if graded
            else None
        )
        return {
            "submitted_count": submitted,
            "graded_count": len(graded),
            "late_count": late,
            "average_marks": round(avg, 2) if avg is not None else None,
        }
