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
