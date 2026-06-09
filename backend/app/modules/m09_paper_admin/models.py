"""
M09 Paper Administration & Scanning — SQLAlchemy models.

Tables (all tenant-schema, no schema= kwarg):
  scanned_script_batches — one record per upload batch (exam bundle workflow)
  scanned_scripts        — one record per uploaded answer script (physical or digital)
  script_evaluations     — one row per question per script per evaluation round
  exam_score_ledger      — append-only finalised marks (written only on Board finalisation)

Human-gate invariants:
  scanned_scripts.status → MARKS_SUBMITTED only via evaluator submit endpoint (Gate 1).
  scanned_scripts.status → BOARD_FINALISED only via board finalise endpoint (Gate 2).
  No Celery task ever sets status beyond SCORED.
  exam_score_ledger is NEVER written by any Celery task.
  script_evaluations.evaluator_marks is NEVER set by any Celery task.
  script_evaluations.board_adjusted_marks is NEVER set by any Celery task.
  scanned_scripts.student_user_id is NEVER returned by any API response
    until status == BOARD_FINALISED.

OCR pipeline (STEP-03):
  ocr_status / ocr_text     — populated by ocr_scanned_script Celery task.
  ocr_quality_score         — overall scan quality 0–100; set by detect_scan_quality task.
  scan_quality_flags        — [{type, page, severity, description}]; set by quality task.
  page_image_keys           — [{page_no, s3_key}]; per-page images for inline viewer.

Double evaluation (STEP-08):
  Controlled by exam_papers.double_evaluation_enabled (M08→M09 integration).
  ScriptEvaluation.evaluation_round: PRIMARY / SECONDARY / MODERATION.
  board_adjusted_marks / board_adjustment_note: Board correction endpoint only (STEP-09).

M09→M10 integration:
  exam_score_ledger.has_board_adjustment: read by M10 BellCurveAnalysis cross-evaluator stats.

Evaluation locking fields (locked_by, locked_at) reserve schema support
  for concurrent-edit prevention; no locking logic in this sprint.

Tenant isolation: all tables live in the tenant schema.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Index, Integer, Numeric, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ScriptStatus(str, enum.Enum):
    PENDING                    = "PENDING"                    # uploaded; queued for quality check
    QUALITY_CHECKING           = "QUALITY_CHECKING"           # detect_scan_quality Celery task running
    QUALITY_FAILED             = "QUALITY_FAILED"             # scan rejected; admin re-uploads
    OCR_PROCESSING             = "OCR_PROCESSING"             # ocr_scanned_script Celery task running
    PROCESSING                 = "PROCESSING"                 # score_scanned_script Celery task running
    SCORED                     = "SCORED"                     # AI scoring complete; awaiting evaluator
    FAILED                     = "FAILED"                     # unrecoverable Celery failure
    REVIEW_REQUIRED            = "REVIEW_REQUIRED"            # partial OCR; evaluator enters manually
    WAITING_SECOND_EVALUATOR   = "WAITING_SECOND_EVALUATOR"   # primary submitted; awaiting secondary
    SECONDARY_EVALUATED        = "SECONDARY_EVALUATED"        # secondary submitted; auto → MARKS_SUBMITTED
    MARKS_SUBMITTED            = "MARKS_SUBMITTED"            # Gate 1 complete; awaiting Board
    BOARD_FINALISED            = "BOARD_FINALISED"            # Gate 2: identity revealed; ledger written


class EvaluationRound(str, enum.Enum):
    """
    Evaluation round for future multi-round moderation workflows.
    PRIMARY   — first evaluator's marks (this sprint)
    SECONDARY — second/re-evaluation (future)
    MODERATION — moderation / challenge recheck (future)
    """
    PRIMARY    = "PRIMARY"
    SECONDARY  = "SECONDARY"
    MODERATION = "MODERATION"


# ---------------------------------------------------------------------------
# ScannedScriptBatch — exam bundle workflow
# ---------------------------------------------------------------------------

class ScannedScriptBatch(Base):
    """
    One upload batch — groups scripts ingested together (e.g. Hall A, Afternoon Session).

    file_count:      number of files included in the batch upload request.
    processed_count: incremented by each script's pipeline completion (success or failure).
    status:
      PENDING    — created; tasks not yet started
      PROCESSING — at least one task running
      COMPLETED  — processed_count == file_count; all succeeded
      PARTIAL    — processed_count == file_count; some QUALITY_FAILED or FAILED
      FAILED     — all scripts failed

    Human-gate: batch status is advisory only; no human gate on the batch itself.
    """
    __tablename__ = "scanned_script_batches"
    __table_args__ = (
        Index("ix_ssb_exam_paper",  "exam_paper_id"),
        Index("ix_ssb_uploaded_by", "uploaded_by"),
        Index("ix_ssb_status",      "status"),
        Index("ix_ssb_created",     "created_at"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_paper_id   = Column(UUID(as_uuid=True), nullable=False)
    uploaded_by     = Column(UUID(as_uuid=True), nullable=False)
    label           = Column(String, nullable=True)
    file_count      = Column(Integer, nullable=False, default=0, server_default="0")
    processed_count = Column(Integer, nullable=False, default=0, server_default="0")
    status          = Column(String, nullable=False, default="PENDING", server_default="PENDING")
    created_at      = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at      = Column(DateTime(timezone=True), nullable=True)

    scripts = relationship(
        "ScannedScript",
        back_populates="batch",
        foreign_keys="ScannedScript.batch_id",
    )


# ---------------------------------------------------------------------------
# ScannedScript
# ---------------------------------------------------------------------------

class ScannedScript(Base):
    """
    One answer script — either a scanned PDF upload (physical paper path)
    or a structured digital submission reference (digital path, future).

    Identity masking:
      student_user_id is stored here but is NEVER returned via API until
      status == BOARD_FINALISED.  Evaluators see only masked_id.

    OCR placeholders (no-op in this sprint):
      ocr_status: e.g. PENDING / PROCESSING / COMPLETE / FAILED
      ocr_text:   raw extracted text from future OCR pipeline

    Locking placeholders (no-op in this sprint):
      locked_by / locked_at: for concurrent-edit prevention
    """
    __tablename__ = "scanned_scripts"
    __table_args__ = (
        Index("ix_scanned_scripts_exam_paper",  "exam_paper_id"),
        Index("ix_scanned_scripts_student",     "student_user_id"),
        Index("ix_scanned_scripts_status",      "status"),
        Index("ix_scanned_scripts_evaluator",   "evaluator_id"),
        Index("ix_scanned_scripts_masked_id",   "masked_id", unique=True),
        Index("ix_scanned_scripts_created",     "created_at"),
        Index("ix_scanned_scripts_batch",       "batch_id"),
        Index("ix_scanned_scripts_duplicate",   "duplicate_of"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # FK to M08 exam_papers.id (cross-module; no SQLAlchemy-level FK enforced
    # because exam_papers lives in the same tenant schema)
    exam_paper_id       = Column(UUID(as_uuid=True), nullable=False)

    # Opaque token shown to evaluators instead of student identity
    masked_id           = Column(String, nullable=False, unique=True)

    # Student identity — stored here but NEVER returned until BOARD_FINALISED
    student_user_id     = Column(UUID(as_uuid=True), nullable=True)
    # Raw roll number / identifier string (optional; admin reconciliation only)
    student_roll_ref    = Column(String, nullable=True)

    # S3 object key for uploaded PDF scan
    upload_url          = Column(String, nullable=True)
    page_count          = Column(Integer, nullable=True)

    # Workflow
    status              = Column(
        Enum(ScriptStatus, native_enum=False),
        nullable=False,
        default=ScriptStatus.PENDING,
    )

    # Celery score task
    eval_job_id         = Column(UUID(as_uuid=True), nullable=True)

    # Objective section auto-score (MCQ marks summed by Celery task)
    objective_auto_score = Column(Numeric(6, 2), nullable=True)

    # Assigned evaluators
    evaluator_id        = Column(UUID(as_uuid=True), nullable=True)
    second_evaluator_id = Column(UUID(as_uuid=True), nullable=True)

    # Double-evaluation — denormalized from exam_papers at ingest; never changed after ingest
    double_evaluation_enabled = Column(Boolean, nullable=False, default=False, server_default="false")

    # Double-evaluation timestamps — written ONLY by submit_marks service on double-eval papers
    primary_submitted_at   = Column(DateTime(timezone=True), nullable=True)
    secondary_submitted_at = Column(DateTime(timezone=True), nullable=True)

    # Gate 1: evaluator submits — written ONLY by submit_marks endpoint
    submitted_by        = Column(UUID(as_uuid=True), nullable=True)
    submitted_at        = Column(DateTime(timezone=True), nullable=True)

    # Gate 2: Board finalises — written ONLY by board_finalise endpoint
    finalised_by        = Column(UUID(as_uuid=True), nullable=True)
    finalised_at        = Column(DateTime(timezone=True), nullable=True)

    # OCR pipeline fields — populated by detect_scan_quality + ocr_scanned_script tasks (STEP-02/03)
    ocr_status          = Column(String, nullable=True)
    ocr_text            = Column(Text, nullable=True)
    ocr_quality_score   = Column(Numeric(4, 2), nullable=True)
    scan_quality_flags  = Column(JSONB, nullable=True)

    # Exam bundle — FK to scanned_script_batches (SET NULL on batch delete)
    batch_id            = Column(
        UUID(as_uuid=True),
        ForeignKey("scanned_script_batches.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Advisory duplicate link — no FK constraint; purely informational
    duplicate_of        = Column(UUID(as_uuid=True), nullable=True)

    # Per-page image S3 keys — [{page_no, s3_key}]; populated by OCR task for inline viewer (STEP-05)
    page_image_keys     = Column(JSONB, nullable=True)

    # Locking placeholders — no locking logic this sprint
    locked_by           = Column(UUID(as_uuid=True), nullable=True)
    locked_at           = Column(DateTime(timezone=True), nullable=True)

    created_at          = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at          = Column(DateTime(timezone=True), nullable=True)

    batch = relationship(
        "ScannedScriptBatch",
        back_populates="scripts",
        foreign_keys=[batch_id],
    )
    evaluations = relationship(
        "ScriptEvaluation",
        back_populates="script",
        cascade="all, delete-orphan",
        order_by="ScriptEvaluation.created_at",
    )
    score_entry = relationship(
        "ExamScoreLedger",
        back_populates="script",
        uselist=False,
    )


# ---------------------------------------------------------------------------
# ScriptEvaluation
# ---------------------------------------------------------------------------

class ScriptEvaluation(Base):
    """
    One evaluation row per question per script per evaluation_round.

    Created by the Celery score task (ai_suggested_marks + ai_justification).
    evaluator_marks is set ONLY by evaluator endpoints — never by Celery.

    evaluation_round supports future multi-round moderation:
      PRIMARY    — first evaluator (this sprint)
      SECONDARY  — re-evaluation (future)
      MODERATION — moderation / challenge (future)

    UniqueConstraint on (script_id, question_id, evaluation_round) ensures
    one row per question per round.
    """
    __tablename__ = "script_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "script_id", "question_id", "evaluation_round",
            name="uq_script_eval_script_question_round",
        ),
        Index("ix_script_evaluations_script",   "script_id"),
        Index("ix_script_evaluations_question",  "question_id"),
        Index("ix_script_evaluations_round",     "evaluation_round"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    script_id           = Column(
        UUID(as_uuid=True),
        ForeignKey("scanned_scripts.id", ondelete="CASCADE"),
        nullable=False,
    )

    # FK to M08 exam_questions.id (same tenant schema; no ORM-level FK here)
    question_id         = Column(UUID(as_uuid=True), nullable=False)

    # Denormalized for display without joining to exam_questions
    question_type       = Column(String, nullable=False)   # MCQ / SHORT_ANSWER / etc.
    max_marks           = Column(Numeric(5, 1), nullable=False)

    # Evaluation round — PRIMARY for this sprint; extensible for SECONDARY/MODERATION
    evaluation_round    = Column(
        Enum(EvaluationRound, native_enum=False),
        nullable=False,
        default=EvaluationRound.PRIMARY,
    )

    # AI suggestion — written by Celery task ONLY
    ai_suggested_marks  = Column(Numeric(5, 1), nullable=True)
    ai_justification    = Column(Text, nullable=True)
    ai_model            = Column(String, nullable=True)
    prompt_hash         = Column(String, nullable=True)

    # AI enrichment — written by score_scanned_script Celery task (STEP-06)
    # [{keyword, found: bool, context: str}]
    keyword_hits        = Column(JSONB, nullable=True)
    # [{criterion, max_marks, suggested_marks, justification}]
    rubric_mapping      = Column(JSONB, nullable=True)
    # Scorer confidence 0.000–1.000
    ai_confidence       = Column(Numeric(4, 3), nullable=True)
    # {start_page: int, end_page: int} — which PDF pages contain this answer
    page_range          = Column(JSONB, nullable=True)

    # Human evaluation — written ONLY by evaluator endpoints, NEVER by Celery
    evaluator_marks     = Column(Numeric(5, 1), nullable=True)
    evaluator_note      = Column(Text, nullable=True)

    # Board correction — written ONLY by Board correction endpoint (STEP-09)
    # NULL = no correction; non-NULL = Board overrides evaluator_marks for final total
    board_adjusted_marks  = Column(Numeric(5, 1), nullable=True)
    board_adjustment_note = Column(Text, nullable=True)

    # Final marks — set on Board finalisation: COALESCE(board_adjusted_marks, evaluator_marks)
    final_marks         = Column(Numeric(5, 1), nullable=True)

    created_at          = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at          = Column(DateTime(timezone=True), nullable=True)

    script = relationship("ScannedScript", back_populates="evaluations")


# ---------------------------------------------------------------------------
# ExamScoreLedger — append-only; no UPDATE or DELETE ever
# ---------------------------------------------------------------------------

class ExamScoreLedger(Base):
    """
    Immutable record of Board-finalised marks for one answer script.

    Written once by board_finalise service method (Gate 2).
    Never updated or deleted — this is the ground truth exam score record.

    student_user_id is denormalized here (from ScannedScript) at write time,
    after identity has been revealed by Board finalisation.

    total_marks: sum of final_marks across all ScriptEvaluation rows at finalise time.
    max_marks:   sum of max_marks across all ScriptEvaluation rows (denormalized).
    """
    __tablename__ = "exam_score_ledger"
    __table_args__ = (
        UniqueConstraint("script_id", name="uq_exam_score_ledger_script"),
        Index("ix_exam_score_ledger_script",      "script_id"),
        Index("ix_exam_score_ledger_exam_paper",  "exam_paper_id"),
        Index("ix_exam_score_ledger_student",     "student_user_id"),
        Index("ix_exam_score_ledger_finalised_by", "finalised_by"),
        Index("ix_exam_score_ledger_finalised_at", "finalised_at"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    script_id           = Column(
        UUID(as_uuid=True),
        ForeignKey("scanned_scripts.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )

    # Denormalized for reporting without joining to scanned_scripts
    exam_paper_id       = Column(UUID(as_uuid=True), nullable=False)
    student_user_id     = Column(UUID(as_uuid=True), nullable=True)
    student_roll_ref    = Column(String, nullable=True)

    # Marks at finalisation time
    total_marks         = Column(Numeric(6, 2), nullable=False)
    max_marks           = Column(Numeric(6, 2), nullable=False)

    # Double-evaluation snapshots — NULL for single-evaluator papers
    primary_total       = Column(Numeric(6, 2), nullable=True)
    secondary_total     = Column(Numeric(6, 2), nullable=True)

    # M09→M10 integration: True when any script_evaluation for this script had
    # board_adjusted_marks set. M10 BellCurveAnalysis reads this flag when computing
    # cross-evaluator anomaly stats to distinguish Board-corrected scores.
    has_board_adjustment = Column(Boolean, nullable=False, default=False, server_default="false")

    # Board member who finalised
    finalised_by        = Column(UUID(as_uuid=True), nullable=False)
    finalisation_note   = Column(Text, nullable=True)
    finalised_at        = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    script = relationship("ScannedScript", back_populates="score_entry")
