"""
M06 — Service layer for the EVALUATOR workflow.

Responsibilities:
  - Manage EvaluatorAssignment records (assign / remove / list).
  - Enforce scope: evaluator can only act on assignments they are mapped to.
  - Wrap existing ReviewService.update_scores for the recommendation path
    so evaluator uses the same rubric-score mechanism but through a
    scope-guarded entry point.
  - Provide analytics aggregation across an evaluator's portfolio.

Human-gate contract preserved:
  - Evaluator writes scores to LabEvaluation (recommendation).
  - Only faculty/admin can ratify (write to grade_ledger).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m06_labs_evaluator.models import (
    EvaluatorAssignment,
    LabAssignment,
    LabSubmission,
    SubmissionStatus,
)
from app.modules.m06_labs_evaluator.repository import (
    AssignmentRepository,
    SubmissionRepository,
)
from app.modules.m06_labs_evaluator.service import LabServiceError, ReviewService


# ---------------------------------------------------------------------------
# EvaluatorService
# ---------------------------------------------------------------------------

class EvaluatorService:

    # -- Evaluator assignment management ------------------------------------

    @staticmethod
    async def assign(
        assignment_id: UUID,
        evaluator_user_id: UUID,
        assigned_by_user_id: UUID,
        db: AsyncSession,
    ) -> EvaluatorAssignment:
        # Verify assignment exists
        assignment = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if assignment is None:
            raise LabServiceError("NOT_FOUND", "Assignment not found.", 404)

        # Upsert: reactivate if previously removed
        result = await db.execute(
            select(EvaluatorAssignment).where(
                EvaluatorAssignment.assignment_id == assignment_id,
                EvaluatorAssignment.evaluator_user_id == evaluator_user_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            if existing.is_active:
                raise LabServiceError(
                    "ALREADY_ASSIGNED",
                    "Evaluator is already assigned to this assignment.",
                    409,
                )
            existing.is_active = True
            await db.commit()
            await db.refresh(existing)
            return existing

        mapping = EvaluatorAssignment(
            assignment_id=assignment_id,
            evaluator_user_id=evaluator_user_id,
            assigned_by_user_id=assigned_by_user_id,
        )
        db.add(mapping)
        await db.commit()
        await db.refresh(mapping)
        return mapping

    @staticmethod
    async def remove(
        assignment_id: UUID,
        evaluator_user_id: UUID,
        db: AsyncSession,
    ) -> None:
        result = await db.execute(
            select(EvaluatorAssignment).where(
                EvaluatorAssignment.assignment_id == assignment_id,
                EvaluatorAssignment.evaluator_user_id == evaluator_user_id,
                EvaluatorAssignment.is_active == True,  # noqa: E712
            )
        )
        mapping = result.scalar_one_or_none()
        if mapping is None:
            raise LabServiceError("NOT_FOUND", "Evaluator assignment not found.", 404)
        mapping.is_active = False
        await db.commit()

    @staticmethod
    async def list_for_assignment(
        assignment_id: UUID,
        db: AsyncSession,
    ) -> list[EvaluatorAssignment]:
        result = await db.execute(
            select(EvaluatorAssignment).where(
                EvaluatorAssignment.assignment_id == assignment_id,
                EvaluatorAssignment.is_active == True,  # noqa: E712
            ).order_by(EvaluatorAssignment.assigned_at)
        )
        return list(result.scalars().all())

    # -- Evaluator scope enforcement ----------------------------------------

    @staticmethod
    async def check_scope(
        evaluator_user_id: UUID,
        assignment_id: UUID,
        db: AsyncSession,
    ) -> bool:
        result = await db.execute(
            select(EvaluatorAssignment.id).where(
                EvaluatorAssignment.evaluator_user_id == evaluator_user_id,
                EvaluatorAssignment.assignment_id == assignment_id,
                EvaluatorAssignment.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def require_scope(
        evaluator_user_id: UUID,
        assignment_id: UUID,
        db: AsyncSession,
    ) -> None:
        if not await EvaluatorService.check_scope(evaluator_user_id, assignment_id, db):
            raise LabServiceError(
                "FORBIDDEN",
                "You are not assigned to this lab assignment.",
                403,
            )

    # -- Evaluator's assignment portfolio -----------------------------------

    @staticmethod
    async def list_assignments(
        evaluator_user_id: UUID,
        db: AsyncSession,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[LabAssignment], int]:
        subq = (
            select(EvaluatorAssignment.assignment_id)
            .where(
                EvaluatorAssignment.evaluator_user_id == evaluator_user_id,
                EvaluatorAssignment.is_active == True,  # noqa: E712
            )
            .scalar_subquery()
        )
        base = select(LabAssignment).where(LabAssignment.id.in_(subq))
        count_q = select(func.count()).select_from(base.subquery())
        total = (await db.execute(count_q)).scalar_one()
        items = (
            await db.execute(
                base.order_by(LabAssignment.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ).scalars().all()
        return list(items), total

    # -- Evaluator recommendation (scope-guarded score update) -------------

    @staticmethod
    async def submit_recommendation(
        submission_id: UUID,
        evaluator_user_id: UUID,
        scores: list,
        db: AsyncSession,
    ):
        sub = await SubmissionRepository.get_by_id(submission_id, db=db)
        if sub is None:
            raise LabServiceError("NOT_FOUND", "Submission not found.", 404)

        await EvaluatorService.require_scope(evaluator_user_id, sub.assignment_id, db)

        # Reuse the existing rubric-score update logic
        evaluation = await ReviewService.update_scores(submission_id, scores, db=db)
        return evaluation

    # -- Evaluator analytics -----------------------------------------------

    @staticmethod
    async def get_analytics(
        evaluator_user_id: UUID,
        db: AsyncSession,
    ) -> dict:
        assigned_q = (
            select(func.count())
            .where(
                EvaluatorAssignment.evaluator_user_id == evaluator_user_id,
                EvaluatorAssignment.is_active == True,  # noqa: E712
            )
        )
        total_assigned = (await db.execute(assigned_q)).scalar_one()

        assignment_ids_q = (
            select(EvaluatorAssignment.assignment_id)
            .where(
                EvaluatorAssignment.evaluator_user_id == evaluator_user_id,
                EvaluatorAssignment.is_active == True,  # noqa: E712
            )
            .scalar_subquery()
        )

        subs_q = select(func.count()).where(
            LabSubmission.assignment_id.in_(assignment_ids_q)
        )
        total_submissions = (await db.execute(subs_q)).scalar_one()

        pending_q = select(func.count()).where(
            LabSubmission.assignment_id.in_(assignment_ids_q),
            LabSubmission.status.in_([
                SubmissionStatus.SUBMITTED,
                SubmissionStatus.EVALUATING,
                SubmissionStatus.EVALUATED,
            ]),
        )
        pending_review = (await db.execute(pending_q)).scalar_one()

        reviewed_q = select(func.count()).where(
            LabSubmission.assignment_id.in_(assignment_ids_q),
            LabSubmission.status == SubmissionStatus.REVIEWED,
        )
        recommended = (await db.execute(reviewed_q)).scalar_one()

        ratified_q = select(func.count()).where(
            LabSubmission.assignment_id.in_(assignment_ids_q),
            LabSubmission.status == SubmissionStatus.RATIFIED,
        )
        ratified = (await db.execute(ratified_q)).scalar_one()

        return {
            "total_assigned":   total_assigned,
            "total_submissions": total_submissions,
            "pending_review":   pending_review,
            "recommended":      recommended,
            "ratified":         ratified,
        }
