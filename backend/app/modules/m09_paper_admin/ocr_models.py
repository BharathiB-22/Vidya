"""
M09.7 OCR Review Queue — SQLAlchemy models.

Tables (tenant-schema):
  ocr_review_queue      — one record per script queued for human OCR review
  ocr_threshold_config  — configurable confidence thresholds (global / exam override)

Priority ordering (highest first):
  4 = OCR_FAILURE        — OCR pipeline returned an error or produced no text
  3 = LOW_CONFIDENCE     — OCR confidence < low_confidence_threshold
  2 = QUALITY_ISSUE      — scan quality flags (CRITICAL/HIGH severity)
  1 = MEDIUM_CONFIDENCE  — OCR confidence between low and medium threshold

Review actions (human gates — never automated):
  ACCEPT        → OCR text accepted as-is; script proceeds normally
  CORRECT       → reviewer edits the OCR text; corrected_text is persisted
  RERUN         → reviewer requests OCR re-extraction (Celery re-queued externally)
  ESCALATE      → script forwarded to Admin for physical intervention
  UNREADABLE    → script declared physically unreadable; manual marks required

Audit integration:
  Every terminal action emits one of the six M09.7 AuditEventType values.
  AI advises, humans decide: no action here autonomously changes marks or status.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Index, Integer,
    Numeric, String, Text, text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OcrPriorityCategory(str, enum.Enum):
    OCR_FAILURE        = "OCR_FAILURE"         # ocr_status = FAILED / no text produced
    LOW_CONFIDENCE     = "LOW_CONFIDENCE"      # confidence < low threshold
    QUALITY_ISSUE      = "QUALITY_ISSUE"       # CRITICAL / HIGH quality flags present
    MEDIUM_CONFIDENCE  = "MEDIUM_CONFIDENCE"   # confidence < medium threshold


# Priority score lookup — higher = reviewed first
PRIORITY_SCORE: dict[str, int] = {
    OcrPriorityCategory.OCR_FAILURE:       4,
    OcrPriorityCategory.LOW_CONFIDENCE:    3,
    OcrPriorityCategory.QUALITY_ISSUE:     2,
    OcrPriorityCategory.MEDIUM_CONFIDENCE: 1,
}


class OcrReviewStatus(str, enum.Enum):
    PENDING           = "PENDING"            # queued; no reviewer yet
    IN_REVIEW         = "IN_REVIEW"          # reviewer opened the item
    ACCEPTED          = "ACCEPTED"           # accepted as-is
    CORRECTED         = "CORRECTED"          # OCR text edited and saved
    RERUN_REQUESTED   = "RERUN_REQUESTED"    # OCR re-run requested
    ESCALATED         = "ESCALATED"          # forwarded to Admin
    MARKED_UNREADABLE = "MARKED_UNREADABLE"  # physically unreadable


class OcrThresholdScope(str, enum.Enum):
    GLOBAL = "GLOBAL"   # institution-wide default
    EXAM   = "EXAM"     # exam-paper-level override


# ---------------------------------------------------------------------------
# OcrReviewQueue
# ---------------------------------------------------------------------------

class OcrReviewQueue(Base):
    """
    One row per script that requires human OCR review.

    Created by the OCR pipeline after processing completes:
      - When ocr_status == FAILED (OCR_FAILURE category)
      - When OCR confidence is below the configured threshold
      - When quality flags are CRITICAL/HIGH severity

    Human-gate invariants:
      - No row is inserted autonomously without a detectable OCR quality problem.
      - review_status is set to terminal states ONLY via the OCR review endpoints.
      - corrected_text is written ONLY by the correct_ocr endpoint.
      - No mark or script status is changed by any action in this table alone;
        the evaluation workflow proceeds independently of review_status.
    """
    __tablename__ = "ocr_review_queue"
    __table_args__ = (
        Index("ix_ocr_queue_script",    "script_id"),
        Index("ix_ocr_queue_paper",     "exam_paper_id"),
        Index("ix_ocr_queue_status",    "review_status"),
        Index("ix_ocr_queue_priority",  "priority_score"),
        Index("ix_ocr_queue_category",  "priority_category"),
        Index("ix_ocr_queue_reviewer",  "assigned_reviewer_id"),
        Index("ix_ocr_queue_created",   "created_at"),
    )

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Link to the script being reviewed
    script_id            = Column(UUID(as_uuid=True), nullable=False)
    exam_paper_id        = Column(UUID(as_uuid=True), nullable=False)  # denormalized

    # Why this script is in the queue
    priority_category    = Column(
        Enum(OcrPriorityCategory, native_enum=False),
        nullable=False,
    )
    priority_score       = Column(Integer, nullable=False)  # 1–4; ORDER BY DESC for queue

    # Snapshot of the OCR confidence at enqueue time (NULL for OCR_FAILURE)
    ocr_confidence       = Column(Numeric(4, 3), nullable=True)

    # Snapshot of the OCR text at enqueue time (what the reviewer will read/correct)
    original_ocr_text    = Column(Text, nullable=True)

    # Workflow state
    review_status        = Column(
        Enum(OcrReviewStatus, native_enum=False),
        nullable=False,
        default=OcrReviewStatus.PENDING,
    )
    assigned_reviewer_id = Column(UUID(as_uuid=True), nullable=True)
    review_started_at    = Column(DateTime(timezone=True), nullable=True)

    # Human-authored content (ONLY set by reviewer endpoints)
    corrected_text       = Column(Text, nullable=True)
    reviewer_notes       = Column(Text, nullable=True)

    # Terminal action taken (matches review_status except PENDING/IN_REVIEW)
    action_taken         = Column(String(30), nullable=True)

    # Completion fields
    completed_by         = Column(UUID(as_uuid=True), nullable=True)
    completed_at         = Column(DateTime(timezone=True), nullable=True)

    created_at           = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at           = Column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# OcrThresholdConfig
# ---------------------------------------------------------------------------

class OcrThresholdConfig(Base):
    """
    Configurable OCR confidence thresholds.

    Scope hierarchy (most specific wins):
      EXAM   (exam_paper_id override)  >  GLOBAL (institution default)

    low_confidence_threshold (default 0.60):
      Scripts with ocr_confidence < this → LOW_CONFIDENCE queue entry.

    medium_confidence_threshold (default 0.80):
      Scripts with confidence in [low, medium) → MEDIUM_CONFIDENCE queue entry.

    Admin-only write.  Changes are audit-logged as OCR_THRESHOLD_UPDATED.
    """
    __tablename__ = "ocr_threshold_config"
    __table_args__ = (
        UniqueConstraint("scope", "scope_ref_id", name="uq_ocr_threshold_scope_ref"),
        Index("ix_ocr_threshold_scope",    "scope"),
        Index("ix_ocr_threshold_ref",      "scope_ref_id"),
        Index("ix_ocr_threshold_active",   "is_active"),
    )

    id                          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope                       = Column(
        Enum(OcrThresholdScope, native_enum=False),
        nullable=False,
    )
    # NULL = GLOBAL; exam_paper_id = EXAM override
    scope_ref_id                = Column(UUID(as_uuid=True), nullable=True)

    low_confidence_threshold    = Column(Numeric(4, 3), nullable=False, default=0.60)
    medium_confidence_threshold = Column(Numeric(4, 3), nullable=False, default=0.80)

    is_active                   = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by                  = Column(UUID(as_uuid=True), nullable=False)
    created_at                  = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at                  = Column(DateTime(timezone=True), nullable=True)
