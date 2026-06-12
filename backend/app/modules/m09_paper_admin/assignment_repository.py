"""
M09.6 Assignment Engine — Repository layer.

All queries run against the tenant search_path set on the session; no
cross-tenant access.  This repository never returns student identity — it only
ever touches the evaluation_assignments table, which by design stores none.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m09_paper_admin.assignment_models import (
    ACTIVE_STATUSES,
    AssignmentStatus,
    EvaluationAssignment,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AssignmentRepository:

    # ------------------------------------------------------------------ create
    @staticmethod
    async def create(
        *,
        assignment_type: str,
        target_entity: str,
        target_id: UUID,
        evaluator_id: UUID,
        assigned_by: UUID,
        exam_paper_id: UUID | None = None,
        evaluation_round: str = "NONE",
        script_code: str | None = None,
        attempt_code: str | None = None,
        priority: int = 0,
        due_at: datetime | None = None,
        notes: str | None = None,
        reassigned_from: UUID | None = None,
        db: AsyncSession,
    ) -> EvaluationAssignment:
        row = EvaluationAssignment(
            assignment_type=assignment_type,
            status=AssignmentStatus.ASSIGNED.value,
            target_entity=target_entity,
            target_id=target_id,
            evaluator_id=evaluator_id,
            assigned_by=assigned_by,
            exam_paper_id=exam_paper_id,
            evaluation_round=evaluation_round or "NONE",
            script_code=script_code,
            attempt_code=attempt_code,
            priority=priority,
            due_at=due_at,
            notes=notes,
            reassigned_from=reassigned_from,
        )
        db.add(row)
        await db.flush()
        return row

    # ------------------------------------------------------------------- reads
    @staticmethod
    async def get_by_id(assignment_id: UUID, *, db: AsyncSession) -> EvaluationAssignment | None:
        res = await db.execute(
            select(EvaluationAssignment).where(EvaluationAssignment.id == assignment_id)
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def get_active_for_target(
        target_entity: str,
        target_id: UUID,
        evaluation_round: str,
        *,
        db: AsyncSession,
    ) -> EvaluationAssignment | None:
        res = await db.execute(
            select(EvaluationAssignment).where(
                EvaluationAssignment.target_entity == target_entity,
                EvaluationAssignment.target_id == target_id,
                EvaluationAssignment.evaluation_round == (evaluation_round or "NONE"),
                EvaluationAssignment.status.in_(ACTIVE_STATUSES),
            )
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def list_filtered(
        *,
        evaluator_id: UUID | None = None,
        assignment_type: str | None = None,
        status: str | None = None,
        exam_paper_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[EvaluationAssignment], int]:
        conds = []
        if evaluator_id is not None:
            conds.append(EvaluationAssignment.evaluator_id == evaluator_id)
        if assignment_type is not None:
            conds.append(EvaluationAssignment.assignment_type == assignment_type)
        if status is not None:
            conds.append(EvaluationAssignment.status == status)
        if exam_paper_id is not None:
            conds.append(EvaluationAssignment.exam_paper_id == exam_paper_id)

        base = select(EvaluationAssignment)
        count_q = select(func.count()).select_from(EvaluationAssignment)
        for c in conds:
            base = base.where(c)
            count_q = count_q.where(c)

        total = (await db.execute(count_q)).scalar_one()
        base = base.order_by(
            EvaluationAssignment.priority.desc(),
            EvaluationAssignment.assigned_at.asc(),
        ).offset(offset).limit(limit)
        rows = list((await db.execute(base)).scalars().all())
        return rows, int(total)

    # ----------------------------------------------------------- status writes
    @staticmethod
    async def set_status(
        assignment_id: UUID,
        new_status: str,
        *,
        timestamp_field: str | None = None,
        reason: str | None = None,
        reassigned_to: UUID | None = None,
        db: AsyncSession,
    ) -> None:
        row = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if row is None:
            return
        row.status = new_status
        if timestamp_field is not None:
            setattr(row, timestamp_field, _utcnow())
        if reason is not None and new_status == AssignmentStatus.CANCELLED.value:
            row.cancel_reason = reason
        if reason is not None and new_status == AssignmentStatus.REASSIGNED.value:
            row.reassign_reason = reason
        if reassigned_to is not None:
            row.reassigned_to = reassigned_to
        await db.flush()

    # --------------------------------------------------------------- workload
    @staticmethod
    async def active_load_for_pool(
        evaluator_ids: list[UUID],
        *,
        db: AsyncSession,
    ) -> dict[str, int]:
        """Map evaluator_id (str) -> count of ACTIVE assignments, for the pool."""
        if not evaluator_ids:
            return {}
        res = await db.execute(
            select(
                EvaluationAssignment.evaluator_id,
                func.count().label("n"),
            )
            .where(
                EvaluationAssignment.evaluator_id.in_(evaluator_ids),
                EvaluationAssignment.status.in_(ACTIVE_STATUSES),
            )
            .group_by(EvaluationAssignment.evaluator_id)
        )
        out = {str(ev): 0 for ev in evaluator_ids}
        for ev_id, n in res.all():
            out[str(ev_id)] = int(n)
        return out

    @staticmethod
    async def workload_summary(
        evaluator_id: UUID,
        *,
        db: AsyncSession,
    ) -> dict:
        """
        Aggregate workload for one evaluator:
          active_count    — ASSIGNED + IN_PROGRESS + SUBMITTED
          pending_count   — ASSIGNED only (not yet started)
          completed_count — COMPLETED
          avg_turnaround_hours — mean(completed_at - assigned_at) over COMPLETED
        """
        # Status counts
        res = await db.execute(
            select(EvaluationAssignment.status, func.count())
            .where(EvaluationAssignment.evaluator_id == evaluator_id)
            .group_by(EvaluationAssignment.status)
        )
        counts = {status: int(n) for status, n in res.all()}

        active = (
            counts.get(AssignmentStatus.ASSIGNED.value, 0)
            + counts.get(AssignmentStatus.IN_PROGRESS.value, 0)
            + counts.get(AssignmentStatus.SUBMITTED.value, 0)
        )
        pending = counts.get(AssignmentStatus.ASSIGNED.value, 0)
        completed = counts.get(AssignmentStatus.COMPLETED.value, 0)

        # Average turnaround in hours over completed assignments
        turn_res = await db.execute(
            select(
                func.avg(
                    func.extract(
                        "epoch",
                        EvaluationAssignment.completed_at - EvaluationAssignment.assigned_at,
                    )
                )
            ).where(
                EvaluationAssignment.evaluator_id == evaluator_id,
                EvaluationAssignment.status == AssignmentStatus.COMPLETED.value,
                EvaluationAssignment.completed_at.isnot(None),
            )
        )
        avg_seconds = turn_res.scalar_one_or_none()
        avg_hours = round(float(avg_seconds) / 3600.0, 2) if avg_seconds else None

        return {
            "evaluator_id": str(evaluator_id),
            "active_count": active,
            "pending_count": pending,
            "in_progress_count": counts.get(AssignmentStatus.IN_PROGRESS.value, 0),
            "submitted_count": counts.get(AssignmentStatus.SUBMITTED.value, 0),
            "completed_count": completed,
            "cancelled_count": counts.get(AssignmentStatus.CANCELLED.value, 0),
            "reassigned_count": counts.get(AssignmentStatus.REASSIGNED.value, 0),
            "avg_turnaround_hours": avg_hours,
        }

    @staticmethod
    async def workload_for_pool(
        evaluator_ids: list[UUID],
        *,
        db: AsyncSession,
    ) -> list[dict]:
        return [
            await AssignmentRepository.workload_summary(ev, db=db)
            for ev in evaluator_ids
        ]
