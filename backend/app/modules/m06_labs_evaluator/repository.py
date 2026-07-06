"""
M06 Labs & Assignment Evaluator — Repository layer.

Classes:
  AssignmentRepository   — CRUD + lifecycle for lab_assignments
  SubmissionRepository   — create, list, status transitions for lab_submissions
  EvaluationRepository   — create / update lab_evaluations (AI results)
  GradeLedgerRepository  — append-only write for grade_ledger (human gate only)

Conventions (mirrors M03/M05):
  - All methods are @staticmethod with keyword-only `db: AsyncSession`.
  - Write methods use db.flush() so callers control commit boundaries.
  - No cross-tenant queries; search_path set at connection time.

Re-exports TaskJobPublicRepository from M02 for Celery job tracking.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.m06_labs_evaluator.models import (
    AIScanStatus,
    AssignmentStatus,
    ConfidenceLevel,
    GradeLedger,
    LabAssignment,
    LabEvaluation,
    LabSubmission,
    SubmissionStatus,
    SubmissionType,
)

# Re-export so callers only need one import path for job tracking.
from app.modules.m02_syllabus.repository import TaskJobPublicRepository  # noqa: F401


# ---------------------------------------------------------------------------
# AssignmentRepository
# ---------------------------------------------------------------------------

class AssignmentRepository:

    @staticmethod
    async def create(
        created_by_user_id: UUID,
        title: str,
        submission_type: SubmissionType,
        rubric: list[dict],
        *,
        syllabus_id: UUID | None = None,
        kit_assignment_id: UUID | None = None,
        description: str | None = None,
        instructions: str | None = None,
        language: str | None = None,
        test_cases: list[dict] | None = None,
        deadline: datetime | None = None,
        ai_not_permitted: bool = True,
        allow_late: bool = False,
        plagiarism_threshold: float = 0.85,
        lab_group: str | None = None,
        program_number: int | None = None,
        db: AsyncSession,
    ) -> LabAssignment:
        obj = LabAssignment(
            created_by_user_id=created_by_user_id,
            title=title,
            submission_type=submission_type,
            rubric=rubric,
            syllabus_id=syllabus_id,
            kit_assignment_id=kit_assignment_id,
            description=description,
            instructions=instructions,
            language=language,
            test_cases=test_cases or [],
            deadline=deadline,
            ai_not_permitted=ai_not_permitted,
            allow_late=allow_late,
            plagiarism_threshold=plagiarism_threshold,
            lab_group=lab_group,
            program_number=program_number,
            status=AssignmentStatus.DRAFT,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def get_by_id(
        assignment_id: UUID,
        *,
        db: AsyncSession,
    ) -> LabAssignment | None:
        result = await db.execute(
            select(LabAssignment).where(LabAssignment.id == assignment_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_assignments(
        *,
        db: AsyncSession,
        syllabus_id: UUID | None = None,
        status: AssignmentStatus | None = None,
        created_by_user_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[LabAssignment], int]:
        filters: list[Any] = []
        if syllabus_id:
            filters.append(LabAssignment.syllabus_id == syllabus_id)
        if status:
            filters.append(LabAssignment.status == status)
        if created_by_user_id:
            filters.append(LabAssignment.created_by_user_id == created_by_user_id)

        count_q = select(func.count()).select_from(LabAssignment)
        items_q = select(LabAssignment).order_by(LabAssignment.created_at.desc())
        if filters:
            count_q = count_q.where(and_(*filters))
            items_q = items_q.where(and_(*filters))

        total  = (await db.execute(count_q)).scalar_one()
        items  = (await db.execute(items_q.offset(offset).limit(limit))).scalars().all()
        return list(items), total

    @staticmethod
    async def update(
        assignment_id: UUID,
        fields: dict[str, Any],
        *,
        db: AsyncSession,
    ) -> LabAssignment | None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await db.execute(
            update(LabAssignment)
            .where(LabAssignment.id == assignment_id)
            .values(**fields)
        )
        await db.flush()
        return await AssignmentRepository.get_by_id(assignment_id, db=db)

    @staticmethod
    async def publish(
        assignment_id: UUID,
        max_marks: int,
        *,
        db: AsyncSession,
    ) -> LabAssignment | None:
        now = datetime.now(timezone.utc)
        await db.execute(
            update(LabAssignment)
            .where(LabAssignment.id == assignment_id)
            .values(
                status=AssignmentStatus.PUBLISHED,
                max_marks=max_marks,
                published_at=now,
                updated_at=now,
            )
        )
        await db.flush()
        return await AssignmentRepository.get_by_id(assignment_id, db=db)

    @staticmethod
    async def close(
        assignment_id: UUID,
        *,
        db: AsyncSession,
    ) -> LabAssignment | None:
        now = datetime.now(timezone.utc)
        await db.execute(
            update(LabAssignment)
            .where(LabAssignment.id == assignment_id)
            .values(
                status=AssignmentStatus.CLOSED,
                closed_at=now,
                updated_at=now,
            )
        )
        await db.flush()
        return await AssignmentRepository.get_by_id(assignment_id, db=db)


# ---------------------------------------------------------------------------
# SubmissionRepository
# ---------------------------------------------------------------------------

class SubmissionRepository:

    @staticmethod
    async def create(
        assignment_id: UUID,
        student_user_id: UUID,
        submission_type: SubmissionType,
        *,
        content_url: str | None = None,
        content_text: str | None = None,
        github_url: str | None = None,
        is_late: bool = False,
        db: AsyncSession,
    ) -> LabSubmission:
        obj = LabSubmission(
            assignment_id=assignment_id,
            student_user_id=student_user_id,
            submission_type=submission_type,
            content_url=content_url,
            content_text=content_text,
            github_url=github_url,
            is_late=is_late,
            ai_scan_status=AIScanStatus.PENDING,
            status=SubmissionStatus.SUBMITTED,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def get_by_id(
        submission_id: UUID,
        *,
        db: AsyncSession,
        load_evaluation: bool = False,
    ) -> LabSubmission | None:
        q = select(LabSubmission).where(LabSubmission.id == submission_id)
        if load_evaluation:
            q = q.options(selectinload(LabSubmission.evaluation))
        result = await db.execute(q)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_student_submission(
        assignment_id: UUID,
        student_user_id: UUID,
        *,
        db: AsyncSession,
    ) -> LabSubmission | None:
        result = await db.execute(
            select(LabSubmission).where(
                and_(
                    LabSubmission.assignment_id == assignment_id,
                    LabSubmission.student_user_id == student_user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_assignment(
        assignment_id: UUID,
        *,
        db: AsyncSession,
        status: SubmissionStatus | None = None,
        ai_scan_status: AIScanStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[LabSubmission], int]:
        filters: list[Any] = [LabSubmission.assignment_id == assignment_id]
        if status:
            filters.append(LabSubmission.status == status)
        if ai_scan_status:
            filters.append(LabSubmission.ai_scan_status == ai_scan_status)

        count_q = select(func.count()).select_from(LabSubmission).where(and_(*filters))
        items_q = (
            select(LabSubmission)
            .where(and_(*filters))
            .options(selectinload(LabSubmission.evaluation))
            .order_by(LabSubmission.submitted_at.asc())
        )
        total = (await db.execute(count_q)).scalar_one()
        items = (await db.execute(items_q.offset(offset).limit(limit))).scalars().all()
        return list(items), total

    @staticmethod
    async def list_for_student(
        student_user_id: UUID,
        *,
        db: AsyncSession,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[LabSubmission], int]:
        filters = [LabSubmission.student_user_id == student_user_id]
        count_q = select(func.count()).select_from(LabSubmission).where(and_(*filters))
        items_q = (
            select(LabSubmission)
            .where(and_(*filters))
            .order_by(LabSubmission.submitted_at.desc())
        )
        total = (await db.execute(count_q)).scalar_one()
        items = (await db.execute(items_q.offset(offset).limit(limit))).scalars().all()
        return list(items), total

    @staticmethod
    async def set_eval_job(
        submission_id: UUID,
        job_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            update(LabSubmission)
            .where(LabSubmission.id == submission_id)
            .values(eval_job_id=job_id, status=SubmissionStatus.EVALUATING)
        )
        await db.flush()

    @staticmethod
    async def set_status(
        submission_id: UUID,
        status: SubmissionStatus,
        *,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            update(LabSubmission)
            .where(LabSubmission.id == submission_id)
            .values(status=status)
        )
        await db.flush()

    @staticmethod
    async def set_ai_scan(
        submission_id: UUID,
        ai_scan_status: AIScanStatus,
        ai_scan_result: dict,
        *,
        db: AsyncSession,
    ) -> None:
        await db.execute(
            update(LabSubmission)
            .where(LabSubmission.id == submission_id)
            .values(ai_scan_status=ai_scan_status, ai_scan_result=ai_scan_result)
        )
        await db.flush()

    @staticmethod
    async def get_cohort_texts(
        assignment_id: UUID,
        exclude_submission_id: UUID,
        *,
        db: AsyncSession,
    ) -> list[tuple[UUID, str]]:
        """Return (submission_id, content_text) for plagiarism comparison."""
        result = await db.execute(
            select(LabSubmission.id, LabSubmission.content_text)
            .where(
                and_(
                    LabSubmission.assignment_id == assignment_id,
                    LabSubmission.id != exclude_submission_id,
                    LabSubmission.content_text.isnot(None),
                )
            )
        )
        return [(row[0], row[1]) for row in result.all()]


# ---------------------------------------------------------------------------
# EvaluationRepository
# ---------------------------------------------------------------------------

class EvaluationRepository:

    @staticmethod
    async def create(
        submission_id: UUID,
        rubric_scores: list[dict],
        overall_ai_score: float,
        confidence_level: ConfidenceLevel,
        *,
        overall_human_score: float | None = None,
        test_results: list[dict] | None = None,
        static_analysis: dict | None = None,
        plagiarism_score: float | None = None,
        plagiarism_matches: list[dict] | None = None,
        ai_model: str | None = None,
        prompt_hash: str | None = None,
        db: AsyncSession,
    ) -> LabEvaluation:
        obj = LabEvaluation(
            submission_id=submission_id,
            rubric_scores=rubric_scores,
            overall_ai_score=overall_ai_score,
            overall_human_score=overall_human_score,
            confidence_level=confidence_level,
            test_results=test_results,
            static_analysis=static_analysis,
            plagiarism_score=plagiarism_score,
            plagiarism_matches=plagiarism_matches,
            ai_model=ai_model,
            prompt_hash=prompt_hash,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def get_by_submission(
        submission_id: UUID,
        *,
        db: AsyncSession,
    ) -> LabEvaluation | None:
        result = await db.execute(
            select(LabEvaluation).where(LabEvaluation.submission_id == submission_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_scores(
        evaluation_id: UUID,
        rubric_scores: list[dict],
        overall_human_score: float,
        *,
        db: AsyncSession,
    ) -> None:
        now = datetime.now(timezone.utc)
        await db.execute(
            update(LabEvaluation)
            .where(LabEvaluation.id == evaluation_id)
            .values(
                rubric_scores=rubric_scores,
                overall_human_score=overall_human_score,
                updated_at=now,
            )
        )
        await db.flush()


# ---------------------------------------------------------------------------
# GradeLedgerRepository  — append-only; called ONLY from ratify endpoint
# ---------------------------------------------------------------------------

class GradeLedgerRepository:

    @staticmethod
    async def get_by_submission(
        submission_id: UUID,
        *,
        db: AsyncSession,
    ) -> GradeLedger | None:
        result = await db.execute(
            select(GradeLedger).where(GradeLedger.submission_id == submission_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        submission_id: UUID,
        assignment_id: UUID,
        student_user_id: UUID,
        ratified_by_user_id: UUID,
        final_score: float,
        max_marks: int,
        *,
        ratification_note: str | None = None,
        db: AsyncSession,
    ) -> GradeLedger:
        """
        Write a ratified grade. Must only be called by the ratify endpoint.
        Will raise IntegrityError if already ratified (unique constraint).
        """
        obj = GradeLedger(
            submission_id=submission_id,
            assignment_id=assignment_id,
            student_user_id=student_user_id,
            ratified_by_user_id=ratified_by_user_id,
            final_score=final_score,
            max_marks=max_marks,
            ratification_note=ratification_note,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj
