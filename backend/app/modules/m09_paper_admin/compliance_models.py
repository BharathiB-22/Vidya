"""
M09.9 Compliance & Audit — SQLAlchemy model.

`exam_mark_audit` is an APPEND-ONLY, immutable, field-level ledger of every
mark mutation in the examination workflow.  It closes the one genuine gap in the
existing audit architecture: the global ``public.audit_logs`` records *that* a
mark changed (and who/when), but not the *previous* and *new* numeric values of
the individual question being changed.  This table records that delta so the
university can always answer:

    Who changed this mark?  When?  Why?  From what value to what value?

Design notes
------------
- Lives in the tenant schema (no ``schema=`` kwarg) — strict tenant isolation.
- One row per (script, question, mutation event).  Many rows per script over its
  lifetime form the complete change history for that script.
- Immutability is enforced at TWO layers:
    1. No repository/service method ever issues UPDATE or DELETE on this table.
    2. A database trigger (``trg_exam_mark_audit_no_change``) rejects UPDATE and
       DELETE outright (see migration 0048ten).  Defence in depth.
- ``student_user_id`` is written ONLY when the underlying script has reached
  BOARD_FINALISED (identity already revealed); it stays NULL before that, so the
  anonymity invariant of the evaluation workflow is preserved in the audit trail.

This table never *drives* any grade decision — it is a passive witness.
("AI advises, humans decide.")
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Column, DateTime, Index, Numeric, String, Text, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base


class MarkChangeType(str, enum.Enum):
    """The kind of mutation that produced this audit row."""
    EVALUATOR_UPDATE  = "EVALUATOR_UPDATE"   # evaluator saved / accepted a per-question mark
    BOARD_ADJUSTMENT  = "BOARD_ADJUSTMENT"   # Board overrode a question mark before finalisation
    MODERATION        = "MODERATION"         # moderator submitted a MODERATION-round mark
    REVALUATION       = "REVALUATION"        # revaluation evaluator changed a mark post-publication


class ExamMarkAudit(Base):
    __tablename__ = "exam_mark_audit"
    __table_args__ = (
        Index("ix_exam_mark_audit_script",     "script_id"),
        Index("ix_exam_mark_audit_question",   "question_id"),
        Index("ix_exam_mark_audit_exam_paper", "exam_paper_id"),
        Index("ix_exam_mark_audit_actor",      "actor_user_id"),
        Index("ix_exam_mark_audit_student",    "student_user_id"),
        Index("ix_exam_mark_audit_type",       "change_type"),
        Index("ix_exam_mark_audit_created",    "created_at"),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # What was changed (polymorphic context, denormalized for query without joins)
    script_id        = Column(UUID(as_uuid=True), nullable=False)
    exam_paper_id    = Column(UUID(as_uuid=True), nullable=False)
    question_id      = Column(UUID(as_uuid=True), nullable=True)   # NULL = script-level total change
    evaluation_round = Column(String(20), nullable=True)

    # Identity — written ONLY after BOARD_FINALISED (NULL preserves anonymity)
    student_user_id  = Column(UUID(as_uuid=True), nullable=True)
    masked_id        = Column(String, nullable=True)              # opaque code, safe pre-finalisation

    change_type      = Column(String(30), nullable=False)

    # The compliance core: previous → new
    previous_marks   = Column(Numeric(6, 2), nullable=True)
    new_marks        = Column(Numeric(6, 2), nullable=True)
    max_marks        = Column(Numeric(6, 2), nullable=True)
    delta            = Column(Numeric(6, 2), nullable=True)        # new - previous (NULL if either side NULL)

    # Who / why
    actor_user_id    = Column(UUID(as_uuid=True), nullable=False)
    actor_role       = Column(String(30), nullable=True)
    reason           = Column(Text, nullable=True)

    # Link back to the canonical event stream (AuditEventType.value at write time)
    source_event     = Column(String(60), nullable=True)
    extra            = Column("metadata", JSONB, nullable=True)

    created_at       = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
