"""
M09.6 Assignment Engine — Service layer.

Orchestrates allocation, lifecycle transitions, reassignment and workload
reporting.  Enforces the engine's invariants:

  * Anonymity   — never reads or returns student identity.
  * Human-decide — COMPLETED is only ever reached by an explicit human action;
                   auto-allocation only *allocates* (no scoring / grading).
  * Duplicate guard — at most one active assignment per (target, round); both a
                   pre-check and the DB partial-unique index protect against it.
  * Audit       — every state change is written to AuditLog.

All public methods are static and take an explicit ``db`` session plus actor
context (acting_user_id / acting_role / tenant_id), mirroring the existing M09
service style.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m09_paper_admin.assignment_allocation import (
    AllocationResult,
    balance_assignments,
)
from app.modules.m09_paper_admin.assignment_models import (
    ACTIVE_STATUSES,
    AssignmentStatus,
    EvaluationAssignment,
)
from app.modules.m09_paper_admin.assignment_repository import AssignmentRepository
from app.modules.m09_paper_admin.assignment_schemas import (
    AssignmentCreateRequest,
    AutoAssignRequest,
    BulkAssignmentRequest,
)


class AssignmentError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _norm_round(value: str | None) -> str:
    return value or "NONE"


async def _audit(event_name: str, *, actor_user_id, actor_role, tenant_id,
                 target_id, metadata: dict) -> None:
    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    await AuditService.log(
        getattr(AuditEventType, event_name),
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        tenant_id=tenant_id,
        schema_name=None,
        target_entity="evaluation_assignment",
        target_id=str(target_id),
        metadata=metadata,
    )


class AssignmentService:

    # ===================================================================== read
    @staticmethod
    async def get(assignment_id: UUID, *, db: AsyncSession) -> EvaluationAssignment:
        row = await AssignmentRepository.get_by_id(assignment_id, db=db)
        if row is None:
            raise AssignmentError("NOT_FOUND", "Assignment not found.", 404)
        return row

    @staticmethod
    async def list(
        *,
        evaluator_id: UUID | None = None,
        assignment_type: str | None = None,
        status: str | None = None,
        exam_paper_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[EvaluationAssignment], int]:
        return await AssignmentRepository.list_filtered(
            evaluator_id=evaluator_id,
            assignment_type=assignment_type,
            status=status,
            exam_paper_id=exam_paper_id,
            offset=offset,
            limit=limit,
            db=db,
        )

    # =================================================================== create
    @staticmethod
    async def create_assignment(
        payload: AssignmentCreateRequest,
        *,
        assigned_by: UUID,
        actor_role: str,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> EvaluationAssignment:
        rnd = _norm_round(payload.evaluation_round)

        existing = await AssignmentRepository.get_active_for_target(
            payload.target_entity, payload.target_id, rnd, db=db
        )
        if existing is not None:
            raise AssignmentError(
                "DUPLICATE_ACTIVE_ASSIGNMENT",
                "An active assignment already exists for this work item and round. "
                "Reassign or cancel the existing one first.",
                409,
            )

        try:
            row = await AssignmentRepository.create(
                assignment_type=payload.assignment_type,
                target_entity=payload.target_entity,
                target_id=payload.target_id,
                evaluator_id=payload.evaluator_id,
                assigned_by=assigned_by,
                exam_paper_id=payload.exam_paper_id,
                evaluation_round=rnd,
                script_code=payload.script_code,
                attempt_code=payload.attempt_code,
                priority=payload.priority,
                due_at=payload.due_at,
                notes=payload.notes,
                db=db,
            )
            await db.commit()
        except IntegrityError:
            # Lost the race against the partial-unique index.
            await db.rollback()
            raise AssignmentError(
                "DUPLICATE_ACTIVE_ASSIGNMENT",
                "An active assignment already exists for this work item and round.",
                409,
            )
        await db.refresh(row)

        await _audit(
            "ASSIGNMENT_CREATED",
            actor_user_id=assigned_by, actor_role=actor_role, tenant_id=tenant_id,
            target_id=row.id,
            metadata={
                "assignment_type": row.assignment_type,
                "target_entity": row.target_entity,
                "target_id": str(row.target_id),
                "evaluator_id": str(row.evaluator_id),
                "evaluation_round": row.evaluation_round,
                "mode": "MANUAL",
            },
        )
        return row

    @staticmethod
    async def bulk_assign(
        payload: BulkAssignmentRequest,
        *,
        assigned_by: UUID,
        actor_role: str,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> tuple[list[EvaluationAssignment], list[dict]]:
        """
        Create many explicit (item, evaluator) assignments.  Items that already
        have an active assignment are skipped (reported back), not failed — the
        rest still commit.  Duplicate target_ids within the same request are
        also de-duplicated.
        """
        created: list[EvaluationAssignment] = []
        skipped: list[dict] = []
        seen_in_request: set[tuple[str, str]] = set()

        for item in payload.items:
            rnd = _norm_round(item.evaluation_round)
            key = (str(item.target_id), rnd)
            if key in seen_in_request:
                skipped.append({"target_id": str(item.target_id), "reason": "DUPLICATE_IN_REQUEST"})
                continue
            seen_in_request.add(key)

            existing = await AssignmentRepository.get_active_for_target(
                payload.target_entity, item.target_id, rnd, db=db
            )
            if existing is not None:
                skipped.append({"target_id": str(item.target_id), "reason": "ALREADY_ASSIGNED"})
                continue

            row = await AssignmentRepository.create(
                assignment_type=payload.assignment_type,
                target_entity=payload.target_entity,
                target_id=item.target_id,
                evaluator_id=item.evaluator_id,
                assigned_by=assigned_by,
                exam_paper_id=payload.exam_paper_id,
                evaluation_round=rnd,
                script_code=item.script_code,
                attempt_code=item.attempt_code,
                priority=payload.priority,
                due_at=payload.due_at,
                db=db,
            )
            created.append(row)

        await db.commit()
        for row in created:
            await db.refresh(row)

        await _audit(
            "ASSIGNMENT_CREATED",
            actor_user_id=assigned_by, actor_role=actor_role, tenant_id=tenant_id,
            target_id=payload.exam_paper_id or "bulk",
            metadata={
                "mode": "BULK",
                "assignment_type": payload.assignment_type,
                "created_count": len(created),
                "skipped_count": len(skipped),
            },
        )
        return created, skipped

    @staticmethod
    async def auto_assign(
        payload: AutoAssignRequest,
        *,
        assigned_by: UUID,
        actor_role: str,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> dict:
        """
        Workload-balanced allocation.

        dry_run=True  → compute and return the plan + projected distribution;
                        nothing is persisted (Admin previews then ratifies).
        dry_run=False → persist the plan, skipping items already actively
                        assigned, and audit AUTO_ASSIGNMENT_EXECUTED.
        """
        pool = [str(e) for e in payload.evaluator_pool]
        target_ids = [str(it.target_id) for it in payload.items]

        # Seed the balancer with each evaluator's *existing* active load so the
        # spread accounts for prior work, not just this batch.
        current_load = await AssignmentRepository.active_load_for_pool(
            payload.evaluator_pool, db=db
        )

        try:
            plan: list[AllocationResult] = balance_assignments(
                target_ids, pool, current_load
            )
        except ValueError as exc:
            raise AssignmentError("EMPTY_POOL", str(exc), 422)

        distribution: dict[str, int] = {ev: 0 for ev in pool}
        for r in plan:
            distribution[r.evaluator_id] += 1

        if payload.dry_run:
            return {
                "dry_run": True,
                "plan": [{"target_id": r.target_id, "evaluator_id": r.evaluator_id} for r in plan],
                "distribution": distribution,
            }

        # Persist — map target_id -> item for code metadata
        item_by_id = {str(it.target_id): it for it in payload.items}
        created: list[EvaluationAssignment] = []
        skipped: list[dict] = []

        for r in plan:
            item = item_by_id[r.target_id]
            rnd = _norm_round(item.evaluation_round)
            existing = await AssignmentRepository.get_active_for_target(
                payload.target_entity, item.target_id, rnd, db=db
            )
            if existing is not None:
                skipped.append({"target_id": r.target_id, "evaluator_id": r.evaluator_id})
                continue
            row = await AssignmentRepository.create(
                assignment_type=payload.assignment_type,
                target_entity=payload.target_entity,
                target_id=item.target_id,
                evaluator_id=UUID(r.evaluator_id),
                assigned_by=assigned_by,
                exam_paper_id=payload.exam_paper_id,
                evaluation_round=rnd,
                script_code=item.script_code,
                attempt_code=item.attempt_code,
                priority=payload.priority,
                due_at=payload.due_at,
                db=db,
            )
            created.append(row)

        await db.commit()
        for row in created:
            await db.refresh(row)

        await _audit(
            "AUTO_ASSIGNMENT_EXECUTED",
            actor_user_id=assigned_by, actor_role=actor_role, tenant_id=tenant_id,
            target_id=payload.exam_paper_id or "auto",
            metadata={
                "assignment_type": payload.assignment_type,
                "pool_size": len(pool),
                "requested": len(target_ids),
                "created_count": len(created),
                "skipped_count": len(skipped),
                "distribution": distribution,
            },
        )
        return {
            "dry_run": False,
            "created": created,
            "skipped": skipped,
            "distribution": distribution,
        }

    # ============================================================ lifecycle
    @staticmethod
    async def _require_owner_or_admin(
        row: EvaluationAssignment, acting_user_id: UUID, acting_role: str
    ) -> None:
        if acting_role == "ADMIN":
            return
        if row.evaluator_id != acting_user_id:
            raise AssignmentError(
                "FORBIDDEN",
                "You may only act on assignments allocated to you.",
                403,
            )

    @staticmethod
    async def start(
        assignment_id: UUID, *, acting_user_id: UUID, acting_role: str,
        tenant_id: UUID, db: AsyncSession,
    ) -> EvaluationAssignment:
        row = await AssignmentService.get(assignment_id, db=db)
        await AssignmentService._require_owner_or_admin(row, acting_user_id, acting_role)
        if row.status != AssignmentStatus.ASSIGNED.value:
            raise AssignmentError(
                "INVALID_TRANSITION",
                f"Can only start an ASSIGNED assignment (current: {row.status}).",
                409,
            )
        await AssignmentRepository.set_status(
            assignment_id, AssignmentStatus.IN_PROGRESS.value,
            timestamp_field="started_at", db=db,
        )
        await db.commit()
        await db.refresh(row)
        await _audit(
            "ASSIGNMENT_STARTED",
            actor_user_id=acting_user_id, actor_role=acting_role, tenant_id=tenant_id,
            target_id=row.id, metadata={"target_id": str(row.target_id)},
        )
        return row

    @staticmethod
    async def submit(
        assignment_id: UUID, *, acting_user_id: UUID, acting_role: str,
        tenant_id: UUID, db: AsyncSession,
    ) -> EvaluationAssignment:
        row = await AssignmentService.get(assignment_id, db=db)
        await AssignmentService._require_owner_or_admin(row, acting_user_id, acting_role)
        if row.status not in (AssignmentStatus.ASSIGNED.value, AssignmentStatus.IN_PROGRESS.value):
            raise AssignmentError(
                "INVALID_TRANSITION",
                f"Can only submit an ASSIGNED/IN_PROGRESS assignment (current: {row.status}).",
                409,
            )
        await AssignmentRepository.set_status(
            assignment_id, AssignmentStatus.SUBMITTED.value,
            timestamp_field="submitted_at", db=db,
        )
        await db.commit()
        await db.refresh(row)
        await _audit(
            "ASSIGNMENT_SUBMITTED",
            actor_user_id=acting_user_id, actor_role=acting_role, tenant_id=tenant_id,
            target_id=row.id, metadata={"target_id": str(row.target_id)},
        )
        return row

    @staticmethod
    async def complete(
        assignment_id: UUID, *, acting_user_id: UUID, acting_role: str,
        tenant_id: UUID, db: AsyncSession,
    ) -> EvaluationAssignment:
        """
        Terminal success.  Human action only — never reached automatically.
        Allowed from SUBMITTED (normal flow) by the owner or an Admin.
        """
        row = await AssignmentService.get(assignment_id, db=db)
        await AssignmentService._require_owner_or_admin(row, acting_user_id, acting_role)
        if row.status != AssignmentStatus.SUBMITTED.value:
            raise AssignmentError(
                "INVALID_TRANSITION",
                f"Can only complete a SUBMITTED assignment (current: {row.status}).",
                409,
            )
        await AssignmentRepository.set_status(
            assignment_id, AssignmentStatus.COMPLETED.value,
            timestamp_field="completed_at", db=db,
        )
        await db.commit()
        await db.refresh(row)
        await _audit(
            "ASSIGNMENT_COMPLETED",
            actor_user_id=acting_user_id, actor_role=acting_role, tenant_id=tenant_id,
            target_id=row.id, metadata={"target_id": str(row.target_id)},
        )
        return row

    @staticmethod
    async def cancel(
        assignment_id: UUID, reason: str, *, acting_user_id: UUID, acting_role: str,
        tenant_id: UUID, db: AsyncSession,
    ) -> EvaluationAssignment:
        row = await AssignmentService.get(assignment_id, db=db)
        if row.status not in ACTIVE_STATUSES:
            raise AssignmentError(
                "INVALID_TRANSITION",
                f"Only an active assignment can be cancelled (current: {row.status}).",
                409,
            )
        await AssignmentRepository.set_status(
            assignment_id, AssignmentStatus.CANCELLED.value,
            timestamp_field="cancelled_at", reason=reason, db=db,
        )
        await db.commit()
        await db.refresh(row)
        await _audit(
            "ASSIGNMENT_CANCELLED",
            actor_user_id=acting_user_id, actor_role=acting_role, tenant_id=tenant_id,
            target_id=row.id, metadata={"target_id": str(row.target_id), "reason": reason},
        )
        return row

    @staticmethod
    async def reassign(
        assignment_id: UUID, new_evaluator_id: UUID, reason: str, *,
        acting_user_id: UUID, acting_role: str, tenant_id: UUID, db: AsyncSession,
    ) -> EvaluationAssignment:
        """
        Move active work to a different evaluator.  The old row is retained as
        REASSIGNED (audit trail); a fresh ASSIGNED row is created for the new
        evaluator.  The chain is linked both ways.
        """
        old = await AssignmentService.get(assignment_id, db=db)
        if old.status not in ACTIVE_STATUSES:
            raise AssignmentError(
                "INVALID_TRANSITION",
                f"Only an active assignment can be reassigned (current: {old.status}).",
                409,
            )
        if old.evaluator_id == new_evaluator_id:
            raise AssignmentError(
                "NO_OP_REASSIGNMENT",
                "New evaluator is the same as the current evaluator.",
                422,
            )

        # Order matters: the partial-unique index allows only ONE active row per
        # (target, round).  We must vacate the predecessor from the active set
        # BEFORE inserting the successor, or the successor's flush collides with
        # the still-active old row.  So: (1) flip old → REASSIGNED, (2) create the
        # successor, (3) back-link old.reassigned_to once the successor has an id.
        await AssignmentRepository.set_status(
            old.id, AssignmentStatus.REASSIGNED.value,
            reason=reason, db=db,
        )
        new_row = await AssignmentRepository.create(
            assignment_type=old.assignment_type,
            target_entity=old.target_entity,
            target_id=old.target_id,
            evaluator_id=new_evaluator_id,
            assigned_by=acting_user_id,
            exam_paper_id=old.exam_paper_id,
            evaluation_round=old.evaluation_round,
            script_code=old.script_code,
            attempt_code=old.attempt_code,
            priority=old.priority,
            due_at=old.due_at,
            notes=old.notes,
            reassigned_from=old.id,
            db=db,
        )
        old.reassigned_to = new_row.id  # back-link the audit chain
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise AssignmentError(
                "DUPLICATE_ACTIVE_ASSIGNMENT",
                "A competing active assignment already exists for this work item.",
                409,
            )
        await db.refresh(new_row)

        await _audit(
            "ASSIGNMENT_REASSIGNED",
            actor_user_id=acting_user_id, actor_role=acting_role, tenant_id=tenant_id,
            target_id=new_row.id,
            metadata={
                "old_assignment_id": str(old.id),
                "from_evaluator": str(old.evaluator_id),
                "to_evaluator": str(new_evaluator_id),
                "target_id": str(old.target_id),
                "reason": reason,
            },
        )
        return new_row

    # ============================================================== workload
    @staticmethod
    async def workload(evaluator_id: UUID, *, db: AsyncSession) -> dict:
        return await AssignmentRepository.workload_summary(evaluator_id, db=db)

    @staticmethod
    async def workload_pool(evaluator_ids: list[UUID], *, db: AsyncSession) -> list[dict]:
        return await AssignmentRepository.workload_for_pool(evaluator_ids, db=db)
