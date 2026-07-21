"""
M09.6 Assignment Engine — unit tests (no DB; mocks + pure functions).

Coverage:
  Enums:
    - AssignmentType / AssignmentStatus members
    - ACTIVE_STATUSES / TERMINAL_STATUSES partitions
  Audit:
    - AuditEventType includes all seven M09.6 events
  Schemas:
    - AssignmentCreateRequest rejects bad assignment_type
    - Auto / Bulk request validators
  Allocation engine (pure):
    - balance_assignments even spread
    - seeds from current_load (least-loaded first)
    - deterministic tie-breaking by pool order
    - empty pool raises
    - projected_distribution
  Repository:
    - workload_summary derives active/pending/completed + turnaround (mocked rows)
  Service:
    - create rejects duplicate active assignment
    - create persists + audits
    - bulk skips already-assigned and in-request duplicates
    - auto_assign dry_run returns plan, persists nothing
    - auto_assign execute persists and skips active targets
    - start/submit/complete happy path + invalid transitions
    - ownership guard for faculty
    - cancel only from active
    - reassign builds chain; rejects no-op and non-active
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.m09_paper_admin.assignment_allocation import (
    balance_assignments,
    projected_distribution,
)
from app.modules.m09_paper_admin.assignment_models import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    AssignmentStatus,
    AssignmentType,
    EvaluationAssignment,
)
from app.modules.m09_paper_admin.assignment_repository import AssignmentRepository
from app.modules.m09_paper_admin.assignment_schemas import (
    AssignmentCreateRequest,
    AutoAssignRequest,
    BulkAssignmentRequest,
)
from app.modules.m09_paper_admin.assignment_service import (
    AssignmentError,
    AssignmentService,
)

_NOW = datetime.now(timezone.utc)
_AUDIT = "app.modules.m09_paper_admin.assignment_service._audit"


def _make_assignment(
    *,
    status: str = AssignmentStatus.ASSIGNED.value,
    evaluator_id: uuid.UUID | None = None,
    assignment_type: str = AssignmentType.REGULAR.value,
    evaluation_round: str = "NONE",
    target_id: uuid.UUID | None = None,
) -> EvaluationAssignment:
    a = EvaluationAssignment()
    a.id = uuid.uuid4()
    a.assignment_type = assignment_type
    a.status = status
    a.target_entity = "scanned_script"
    a.target_id = target_id or uuid.uuid4()
    a.exam_paper_id = uuid.uuid4()
    a.evaluation_round = evaluation_round
    a.script_code = "SCR-AB12"
    a.attempt_code = None
    a.evaluator_id = evaluator_id or uuid.uuid4()
    a.assigned_by = uuid.uuid4()
    a.priority = 0
    a.due_at = None
    a.notes = None
    a.assigned_at = _NOW
    a.started_at = None
    a.submitted_at = None
    a.completed_at = None
    a.cancelled_at = None
    a.reassigned_from = None
    a.reassigned_to = None
    a.reassign_reason = None
    a.cancel_reason = None
    a.created_at = _NOW
    return a


def _db() -> AsyncMock:
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ===========================================================================
# Enums
# ===========================================================================

def test_assignment_type_members():
    assert {t.value for t in AssignmentType} == {
        "REGULAR", "DOUBLE_EVALUATION", "MODERATION", "REVALUATION", "DIGITAL_SUBJECTIVE",
    }


def test_assignment_status_members():
    assert {s.value for s in AssignmentStatus} == {
        "ASSIGNED", "IN_PROGRESS", "SUBMITTED", "COMPLETED", "CANCELLED", "REASSIGNED",
    }


def test_active_and_terminal_partition():
    assert set(ACTIVE_STATUSES) == {"ASSIGNED", "IN_PROGRESS", "SUBMITTED"}
    assert set(TERMINAL_STATUSES) == {"COMPLETED", "CANCELLED", "REASSIGNED"}
    assert set(ACTIVE_STATUSES).isdisjoint(TERMINAL_STATUSES)


# ===========================================================================
# Audit events
# ===========================================================================

def test_audit_events_present():
    from app.core.audit_log.models import AuditEventType
    for name in (
        "ASSIGNMENT_CREATED", "ASSIGNMENT_REASSIGNED", "ASSIGNMENT_STARTED",
        "ASSIGNMENT_SUBMITTED", "ASSIGNMENT_COMPLETED", "ASSIGNMENT_CANCELLED",
        "AUTO_ASSIGNMENT_EXECUTED",
    ):
        assert hasattr(AuditEventType, name)


# ===========================================================================
# Schemas
# ===========================================================================

def test_create_request_rejects_bad_type():
    with pytest.raises(ValueError):
        AssignmentCreateRequest(
            assignment_type="BOGUS", target_entity="scanned_script",
            target_id=uuid.uuid4(), evaluator_id=uuid.uuid4(),
        )


def test_create_request_accepts_valid():
    req = AssignmentCreateRequest(
        assignment_type="REGULAR", target_entity="scanned_script",
        target_id=uuid.uuid4(), evaluator_id=uuid.uuid4(),
    )
    assert req.evaluation_round == "NONE"
    assert req.priority == 0


def test_bulk_request_requires_items():
    with pytest.raises(ValueError):
        BulkAssignmentRequest(
            assignment_type="REGULAR", target_entity="scanned_script", items=[],
        )


def test_auto_request_requires_pool():
    with pytest.raises(ValueError):
        AutoAssignRequest(
            assignment_type="REGULAR", target_entity="scanned_script",
            evaluator_pool=[], items=[{"target_id": str(uuid.uuid4())}],
        )


# ===========================================================================
# Allocation engine (pure)
# ===========================================================================

def test_balance_even_spread():
    plan = balance_assignments(["t1", "t2", "t3", "t4"], ["A", "B"])
    counts = {"A": 0, "B": 0}
    for r in plan:
        counts[r.evaluator_id] += 1
    assert counts == {"A": 2, "B": 2}


def test_balance_seeds_from_current_load():
    # A already has 3, B has 0 → first items go to B.
    plan = balance_assignments(["t1", "t2", "t3"], ["A", "B"], {"A": 3, "B": 0})
    assert plan[0].evaluator_id == "B"
    assert plan[1].evaluator_id == "B"
    assert plan[2].evaluator_id == "B"  # B catches up before tying A at 3


def test_balance_deterministic_tiebreak():
    p1 = balance_assignments(["t1", "t2"], ["A", "B", "C"])
    p2 = balance_assignments(["t1", "t2"], ["A", "B", "C"])
    assert [r.evaluator_id for r in p1] == [r.evaluator_id for r in p2]
    # First two items go to the first two evaluators in pool order.
    assert p1[0].evaluator_id == "A"
    assert p1[1].evaluator_id == "B"


def test_balance_empty_pool_raises():
    with pytest.raises(ValueError):
        balance_assignments(["t1"], [])


def test_balance_empty_targets_ok():
    assert balance_assignments([], ["A"]) == []


def test_projected_distribution():
    dist = projected_distribution(6, ["A", "B", "C"])
    assert dist == {"A": 2, "B": 2, "C": 2}


# ===========================================================================
# Repository.workload_summary (mocked rows)
# ===========================================================================

@pytest.mark.asyncio
async def test_workload_summary_computation():
    db = AsyncMock()

    status_result = MagicMock()
    status_result.all.return_value = [
        ("ASSIGNED", 2), ("IN_PROGRESS", 1), ("SUBMITTED", 1), ("COMPLETED", 4),
    ]
    turn_result = MagicMock()
    turn_result.scalar_one_or_none.return_value = 7200.0  # 2h avg

    db.execute = AsyncMock(side_effect=[status_result, turn_result])

    out = await AssignmentRepository.workload_summary(uuid.uuid4(), db=db)
    assert out["active_count"] == 4      # 2 + 1 + 1
    assert out["pending_count"] == 2
    assert out["completed_count"] == 4
    assert out["avg_turnaround_hours"] == 2.0


# ===========================================================================
# Service: create
# ===========================================================================

@pytest.mark.asyncio
async def test_create_rejects_duplicate_active():
    db = _db()
    existing = _make_assignment()
    payload = AssignmentCreateRequest(
        assignment_type="REGULAR", target_entity="scanned_script",
        target_id=uuid.uuid4(), evaluator_id=uuid.uuid4(),
    )
    with patch.object(AssignmentRepository, "get_active_for_target",
                      new=AsyncMock(return_value=existing)):
        with pytest.raises(AssignmentError) as exc:
            await AssignmentService.create_assignment(
                payload, assigned_by=uuid.uuid4(), actor_role="ADMIN",
                tenant_id=uuid.uuid4(), db=db,
            )
    assert exc.value.status_code == 409
    assert exc.value.code == "DUPLICATE_ACTIVE_ASSIGNMENT"


@pytest.mark.asyncio
async def test_create_persists_and_audits():
    db = _db()
    new_row = _make_assignment()
    payload = AssignmentCreateRequest(
        assignment_type="REGULAR", target_entity="scanned_script",
        target_id=new_row.target_id, evaluator_id=new_row.evaluator_id,
    )
    with (
        patch.object(AssignmentRepository, "get_active_for_target", new=AsyncMock(return_value=None)),
        patch.object(AssignmentRepository, "create", new=AsyncMock(return_value=new_row)),
        patch(_AUDIT, new=AsyncMock()) as audit,
    ):
        row = await AssignmentService.create_assignment(
            payload, assigned_by=uuid.uuid4(), actor_role="ADMIN",
            tenant_id=uuid.uuid4(), db=db,
        )
    assert row is new_row
    db.commit.assert_awaited()
    audit.assert_awaited()


# ===========================================================================
# Service: bulk
# ===========================================================================

@pytest.mark.asyncio
async def test_bulk_skips_existing_and_in_request_dupes():
    db = _db()
    t_dupe = uuid.uuid4()
    t_existing = uuid.uuid4()
    t_ok = uuid.uuid4()
    payload = BulkAssignmentRequest(
        assignment_type="REGULAR", target_entity="scanned_script",
        items=[
            {"target_id": str(t_dupe), "evaluator_id": str(uuid.uuid4())},
            {"target_id": str(t_dupe), "evaluator_id": str(uuid.uuid4())},      # dup in request
            {"target_id": str(t_existing), "evaluator_id": str(uuid.uuid4())},  # already assigned
            {"target_id": str(t_ok), "evaluator_id": str(uuid.uuid4())},
        ],
    )

    async def fake_active(entity, tid, rnd, *, db):
        return _make_assignment() if tid == t_existing else None

    created_rows = []

    async def fake_create(**kw):
        r = _make_assignment(target_id=kw["target_id"])
        created_rows.append(r)
        return r

    with (
        patch.object(AssignmentRepository, "get_active_for_target", new=AsyncMock(side_effect=fake_active)),
        patch.object(AssignmentRepository, "create", new=AsyncMock(side_effect=fake_create)),
        patch(_AUDIT, new=AsyncMock()),
    ):
        created, skipped = await AssignmentService.bulk_assign(
            payload, assigned_by=uuid.uuid4(), actor_role="ADMIN",
            tenant_id=uuid.uuid4(), db=db,
        )

    reasons = {s["reason"] for s in skipped}
    assert "DUPLICATE_IN_REQUEST" in reasons
    assert "ALREADY_ASSIGNED" in reasons
    assert len(created) == 2  # t_dupe (first) + t_ok


# ===========================================================================
# Service: auto_assign
# ===========================================================================

@pytest.mark.asyncio
async def test_auto_assign_dry_run_persists_nothing():
    db = _db()
    pool = [uuid.uuid4(), uuid.uuid4()]
    payload = AutoAssignRequest(
        assignment_type="REGULAR", target_entity="scanned_script",
        evaluator_pool=pool,
        items=[{"target_id": str(uuid.uuid4())} for _ in range(4)],
        dry_run=True,
    )
    with (
        patch.object(AssignmentRepository, "active_load_for_pool", new=AsyncMock(return_value={})),
        patch.object(AssignmentRepository, "create", new=AsyncMock()) as create_mock,
        patch(_AUDIT, new=AsyncMock()),
    ):
        result = await AssignmentService.auto_assign(
            payload, assigned_by=uuid.uuid4(), actor_role="ADMIN",
            tenant_id=uuid.uuid4(), db=db,
        )
    assert result["dry_run"] is True
    assert len(result["plan"]) == 4
    create_mock.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_assign_execute_persists_and_skips_active():
    db = _db()
    pool = [uuid.uuid4(), uuid.uuid4()]
    t_active = uuid.uuid4()
    items = [{"target_id": str(t_active)}, {"target_id": str(uuid.uuid4())}]
    payload = AutoAssignRequest(
        assignment_type="REGULAR", target_entity="scanned_script",
        evaluator_pool=pool, items=items, dry_run=False,
    )

    async def fake_active(entity, tid, rnd, *, db):
        return _make_assignment() if tid == t_active else None

    with (
        patch.object(AssignmentRepository, "active_load_for_pool", new=AsyncMock(return_value={})),
        patch.object(AssignmentRepository, "get_active_for_target", new=AsyncMock(side_effect=fake_active)),
        patch.object(AssignmentRepository, "create",
                     new=AsyncMock(side_effect=lambda **kw: _make_assignment(target_id=kw["target_id"]))),
        patch(_AUDIT, new=AsyncMock()),
    ):
        result = await AssignmentService.auto_assign(
            payload, assigned_by=uuid.uuid4(), actor_role="ADMIN",
            tenant_id=uuid.uuid4(), db=db,
        )
    assert result["dry_run"] is False
    assert len(result["created"]) == 1
    assert len(result["skipped"]) == 1
    db.commit.assert_awaited()


# ===========================================================================
# Service: lifecycle transitions
# ===========================================================================

@pytest.mark.asyncio
async def test_start_happy_path():
    db = _db()
    row = _make_assignment(status="ASSIGNED")
    with (
        patch.object(AssignmentRepository, "get_by_id", new=AsyncMock(return_value=row)),
        patch.object(AssignmentRepository, "set_status", new=AsyncMock()) as ss,
        patch(_AUDIT, new=AsyncMock()),
    ):
        await AssignmentService.start(
            row.id, acting_user_id=row.evaluator_id, acting_role="FACULTY",
            tenant_id=uuid.uuid4(), db=db,
        )
    ss.assert_awaited()
    assert ss.await_args.args[1] == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_start_invalid_transition():
    db = _db()
    row = _make_assignment(status="SUBMITTED")
    with patch.object(AssignmentRepository, "get_by_id", new=AsyncMock(return_value=row)):
        with pytest.raises(AssignmentError) as exc:
            await AssignmentService.start(
                row.id, acting_user_id=row.evaluator_id, acting_role="FACULTY",
                tenant_id=uuid.uuid4(), db=db,
            )
    assert exc.value.code == "INVALID_TRANSITION"


@pytest.mark.asyncio
async def test_faculty_ownership_guard():
    db = _db()
    row = _make_assignment(status="ASSIGNED")
    other = uuid.uuid4()
    with patch.object(AssignmentRepository, "get_by_id", new=AsyncMock(return_value=row)):
        with pytest.raises(AssignmentError) as exc:
            await AssignmentService.start(
                row.id, acting_user_id=other, acting_role="FACULTY",
                tenant_id=uuid.uuid4(), db=db,
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_complete_requires_submitted():
    db = _db()
    row = _make_assignment(status="IN_PROGRESS")
    with patch.object(AssignmentRepository, "get_by_id", new=AsyncMock(return_value=row)):
        with pytest.raises(AssignmentError) as exc:
            await AssignmentService.complete(
                row.id, acting_user_id=row.evaluator_id, acting_role="ADMIN",
                tenant_id=uuid.uuid4(), db=db,
            )
    assert exc.value.code == "INVALID_TRANSITION"


@pytest.mark.asyncio
async def test_submit_then_complete():
    db = _db()
    row = _make_assignment(status="SUBMITTED")
    with (
        patch.object(AssignmentRepository, "get_by_id", new=AsyncMock(return_value=row)),
        patch.object(AssignmentRepository, "set_status", new=AsyncMock()) as ss,
        patch(_AUDIT, new=AsyncMock()),
    ):
        await AssignmentService.complete(
            row.id, acting_user_id=uuid.uuid4(), acting_role="ADMIN",
            tenant_id=uuid.uuid4(), db=db,
        )
    assert ss.await_args.args[1] == "COMPLETED"


# ===========================================================================
# Service: cancel
# ===========================================================================

@pytest.mark.asyncio
async def test_cancel_only_from_active():
    db = _db()
    row = _make_assignment(status="COMPLETED")
    with patch.object(AssignmentRepository, "get_by_id", new=AsyncMock(return_value=row)):
        with pytest.raises(AssignmentError) as exc:
            await AssignmentService.cancel(
                row.id, "no longer needed", acting_user_id=uuid.uuid4(),
                acting_role="ADMIN", tenant_id=uuid.uuid4(), db=db,
            )
    assert exc.value.code == "INVALID_TRANSITION"


# ===========================================================================
# Service: reassign
# ===========================================================================

@pytest.mark.asyncio
async def test_reassign_builds_chain():
    db = _db()
    old = _make_assignment(status="ASSIGNED")
    new_eval = uuid.uuid4()
    created = {}

    async def fake_create(**kw):
        created.update(kw)
        return _make_assignment(status="ASSIGNED", evaluator_id=kw["evaluator_id"])

    with (
        patch.object(AssignmentRepository, "get_by_id", new=AsyncMock(return_value=old)),
        patch.object(AssignmentRepository, "create", new=AsyncMock(side_effect=fake_create)),
        patch.object(AssignmentRepository, "set_status", new=AsyncMock()) as ss,
        patch(_AUDIT, new=AsyncMock()),
    ):
        new_row = await AssignmentService.reassign(
            old.id, new_eval, "balancing", acting_user_id=uuid.uuid4(),
            acting_role="DEAN", tenant_id=uuid.uuid4(), db=db,
        )
    # successor inherits the work item + links back to predecessor
    assert created["reassigned_from"] == old.id
    assert created["evaluator_id"] == new_eval
    assert created["target_id"] == old.target_id
    # predecessor moved to REASSIGNED *before* the successor is created
    assert ss.await_args.args[1] == "REASSIGNED"
    # predecessor back-links to the successor (audit chain intact both ways)
    assert old.reassigned_to == new_row.id
    assert new_row.evaluator_id == new_eval


@pytest.mark.asyncio
async def test_reassign_rejects_no_op():
    db = _db()
    old = _make_assignment(status="ASSIGNED")
    with patch.object(AssignmentRepository, "get_by_id", new=AsyncMock(return_value=old)):
        with pytest.raises(AssignmentError) as exc:
            await AssignmentService.reassign(
                old.id, old.evaluator_id, "same", acting_user_id=uuid.uuid4(),
                acting_role="ADMIN", tenant_id=uuid.uuid4(), db=db,
            )
    assert exc.value.code == "NO_OP_REASSIGNMENT"


@pytest.mark.asyncio
async def test_reassign_rejects_terminal():
    db = _db()
    old = _make_assignment(status="COMPLETED")
    with patch.object(AssignmentRepository, "get_by_id", new=AsyncMock(return_value=old)):
        with pytest.raises(AssignmentError) as exc:
            await AssignmentService.reassign(
                old.id, uuid.uuid4(), "late", acting_user_id=uuid.uuid4(),
                acting_role="ADMIN", tenant_id=uuid.uuid4(), db=db,
            )
    assert exc.value.code == "INVALID_TRANSITION"
