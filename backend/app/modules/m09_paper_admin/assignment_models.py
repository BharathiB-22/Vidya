"""
M09.6 Assignment Engine — SQLAlchemy model.

A single unified ledger of evaluation work allocated to faculty/evaluators.
It is deliberately decoupled from the work-item tables (scanned_scripts,
digital_exam_attempts, revaluation_requests) so that any current OR future
evaluation workflow can allocate work through one engine.

Polymorphic target
------------------
  target_entity + target_id identify the underlying work item, e.g.
    ("scanned_script",      <script_id>)        — REGULAR / DOUBLE_EVALUATION / MODERATION
    ("revaluation_request", <reval_request_id>)  — REVALUATION
    ("digital_exam_attempt",<attempt_id>)        — DIGITAL_SUBJECTIVE
  No ORM-level FK is declared because target tables differ per type; integrity
  is enforced in the service layer.

Anonymity invariant (non-negotiable)
------------------------------------
  This table NEVER stores student identity.  Faculty see only:
    script_code   — opaque code (e.g. scanned_scripts.masked_id)
    attempt_code  — opaque code for digital attempts
  No API response derived from this table may include student_user_id, name or
  roll number.  Identity continues to be revealed only by the existing M09
  Board-finalisation gate on the underlying work item.

Human-decide invariant
----------------------
  An assignment allocates WORK; it never applies a grade, penalty or rejection.
  status → COMPLETED is only ever set by the assigned human faculty action.
  Auto-allocation is deterministic workload balancing (no AI, no scoring).

Reassignment audit trail
------------------------
  Reassigning never mutates evaluator_id in place.  The old row is moved to
  status=REASSIGNED with reassigned_to pointing at the new row; the new row
  carries reassigned_from.  The full chain is therefore preserved forever.

Active-assignment uniqueness
----------------------------
  At most one ACTIVE assignment may exist per
    (target_entity, target_id, evaluation_round)
  enforced by a partial unique index over active statuses.  This is the primary
  guard against duplicate / racing assignments.

Tenant isolation: lives in the tenant schema (no schema= kwarg).
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, String, Text, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AssignmentType(str, enum.Enum):
    """The evaluation workflow this assignment feeds."""
    REGULAR            = "REGULAR"             # single-evaluator script marking
    DOUBLE_EVALUATION  = "DOUBLE_EVALUATION"   # primary/secondary parallel marking
    MODERATION         = "MODERATION"          # variance moderation review
    REVALUATION        = "REVALUATION"         # post-publication revaluation
    DIGITAL_SUBJECTIVE = "DIGITAL_SUBJECTIVE"  # digital exam subjective scoring


class AssignmentStatus(str, enum.Enum):
    """
    Lifecycle of one assignment.

      ASSIGNED    — allocated to an evaluator; work not started
      IN_PROGRESS — evaluator opened / started the work
      SUBMITTED   — evaluator submitted their marks for this work item
      COMPLETED   — terminal success; the underlying gate accepted the work
      CANCELLED   — terminal; allocation withdrawn (work item not needed)
      REASSIGNED  — terminal; superseded by a newer assignment row
    """
    ASSIGNED    = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED   = "SUBMITTED"
    COMPLETED   = "COMPLETED"
    CANCELLED   = "CANCELLED"
    REASSIGNED  = "REASSIGNED"


# Statuses that count as "active" (an evaluator still owns the work).
ACTIVE_STATUSES = (
    AssignmentStatus.ASSIGNED.value,
    AssignmentStatus.IN_PROGRESS.value,
    AssignmentStatus.SUBMITTED.value,
)

# Statuses that are terminal (no further transitions allowed).
TERMINAL_STATUSES = (
    AssignmentStatus.COMPLETED.value,
    AssignmentStatus.CANCELLED.value,
    AssignmentStatus.REASSIGNED.value,
)


# ---------------------------------------------------------------------------
# EvaluationAssignment
# ---------------------------------------------------------------------------

class EvaluationAssignment(Base):
    __tablename__ = "evaluation_assignments"
    __table_args__ = (
        Index("ix_eval_assignments_evaluator",   "evaluator_id"),
        Index("ix_eval_assignments_status",      "status"),
        Index("ix_eval_assignments_type",        "assignment_type"),
        Index("ix_eval_assignments_target",      "target_entity", "target_id"),
        Index("ix_eval_assignments_exam_paper",  "exam_paper_id"),
        Index("ix_eval_assignments_assigned_by", "assigned_by"),
        Index("ix_eval_assignments_created",     "created_at"),
        # Primary duplicate guard: only ONE active assignment per work item + round.
        # Partial unique index (status active) — created explicitly in the migration.
        Index(
            "uq_eval_assignments_active_target",
            "target_entity", "target_id", "evaluation_round",
            unique=True,
            postgresql_where=text(
                "status IN ('ASSIGNED','IN_PROGRESS','SUBMITTED')"
            ),
        ),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    assignment_type  = Column(String(30), nullable=False)
    status           = Column(
        String(20), nullable=False,
        default=AssignmentStatus.ASSIGNED.value,
        server_default=AssignmentStatus.ASSIGNED.value,
    )

    # Polymorphic work-item reference
    target_entity    = Column(String(40), nullable=False)
    target_id        = Column(UUID(as_uuid=True), nullable=False)

    # Denormalized context (no PII)
    exam_paper_id    = Column(UUID(as_uuid=True), nullable=True)
    # Round for double-evaluation / moderation chains (NULL for single rounds).
    # Stored as plain string so the active-uniqueness index treats NULL rounds
    # as distinct per Postgres NULL semantics — see service-layer guard.
    evaluation_round = Column(String(20), nullable=False, server_default="NONE", default="NONE")

    # Anonymous codes shown to faculty (NEVER student identity)
    script_code      = Column(String, nullable=True)
    attempt_code     = Column(String, nullable=True)

    # Allocation
    evaluator_id     = Column(UUID(as_uuid=True), nullable=False)
    assigned_by      = Column(UUID(as_uuid=True), nullable=False)
    priority         = Column(Integer, nullable=False, server_default="0", default=0)
    due_at           = Column(DateTime(timezone=True), nullable=True)
    notes            = Column(Text, nullable=True)

    # Lifecycle timestamps
    assigned_at      = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    started_at       = Column(DateTime(timezone=True), nullable=True)
    submitted_at     = Column(DateTime(timezone=True), nullable=True)
    completed_at     = Column(DateTime(timezone=True), nullable=True)
    cancelled_at     = Column(DateTime(timezone=True), nullable=True)

    # Reassignment chain (self-referential, no cascade — audit trail is permanent)
    reassigned_from  = Column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_assignments.id", ondelete="SET NULL"),
        nullable=True,
    )
    reassigned_to    = Column(UUID(as_uuid=True), nullable=True)
    reassign_reason  = Column(Text, nullable=True)
    cancel_reason    = Column(Text, nullable=True)

    created_at       = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at       = Column(DateTime(timezone=True), nullable=True, onupdate=text("now()"))

    predecessor = relationship(
        "EvaluationAssignment",
        remote_side=[id],
        foreign_keys=[reassigned_from],
        uselist=False,
    )
