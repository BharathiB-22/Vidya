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
    SECONDARY_EVALUATED        = "SECONDARY_EVALUATED"        # secondary submitted; variance check pending
    MARKS_SUBMITTED            = "MARKS_SUBMITTED"            # Gate 1 complete; awaiting Board
    MODERATION_PENDING         = "MODERATION_PENDING"         # M09.2: variance exceeded; awaiting moderator
    MODERATION_COMPLETE        = "MODERATION_COMPLETE"        # M09.2: moderator submitted; awaiting Board
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


class BoardSessionStatus(str, enum.Enum):
    """Lifecycle of an Examination Board results-approval session."""
    OPEN     = "OPEN"      # session created; awaiting decision
    APPROVED = "APPROVED"  # Board approved; results locked
    REJECTED = "REJECTED"  # Board rejected; scripts returned for review
    DECLARED = "DECLARED"  # Admin published results to students


class BoardApprovalStatus(str, enum.Enum):
    """Approval status of a course within a board session."""
    PENDING  = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


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
    moderation_review = relationship(
        "ScriptModerationReview",
        back_populates="script",
        uselist=False,
        cascade="all, delete-orphan",
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
# ScriptModerationReview — M09.2
# ---------------------------------------------------------------------------

class ModerationStatus(str, enum.Enum):
    PENDING  = "PENDING"   # flagged; awaiting moderator
    COMPLETE = "COMPLETE"  # moderator submitted MODERATION round marks
    SKIPPED  = "SKIPPED"   # flagged but Board overrode without moderation


class ScriptModerationReview(Base):
    """
    One row per moderation event for a scanned script.

    Created when variance between primary and secondary evaluator totals
    exceeds exam_papers.discrepancy_threshold_pct (auto-flag), or when a
    Dean/Admin manually flags a MARKS_SUBMITTED script.

    flagged_by = NULL means auto-flagged by the system.
    moderator_id / moderation_notes are set when the moderator submits.

    Invariants:
      - Written ONLY by ModerationService; never by Celery.
      - Original evaluator marks (PRIMARY / SECONDARY rounds) are immutable
        after moderation is created.
      - Moderated marks are stored as MODERATION round ScriptEvaluation rows.
    """
    __tablename__ = "script_moderation_reviews"
    __table_args__ = (
        Index("ix_moderation_reviews_script",     "script_id"),
        Index("ix_moderation_reviews_exam_paper", "exam_paper_id"),
        Index("ix_moderation_reviews_status",     "status"),
        Index("ix_moderation_reviews_moderator",  "moderator_id"),
        Index("ix_moderation_reviews_created",    "created_at"),
    )

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    script_id          = Column(
        UUID(as_uuid=True),
        ForeignKey("scanned_scripts.id", ondelete="CASCADE"),
        nullable=False,
    )
    exam_paper_id      = Column(UUID(as_uuid=True), nullable=False)  # denormalized

    # Evaluator totals at the time of flagging (snapshot — immutable after creation)
    primary_total      = Column(Numeric(6, 2), nullable=False)
    secondary_total    = Column(Numeric(6, 2), nullable=False)
    variance_pct       = Column(Numeric(5, 2), nullable=False)  # abs(P-S)/max*100
    variance_threshold = Column(Numeric(5, 2), nullable=False)  # threshold that was in effect

    # Why flagged: "AUTO_VARIANCE" or a free-text reason from Dean/Admin
    flag_reason        = Column(Text, nullable=False)
    # NULL = auto-flagged by system; non-NULL = flagged by a named human
    flagged_by         = Column(UUID(as_uuid=True), nullable=True)
    flagged_at         = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    # Moderation outcome — populated when moderator submits
    moderator_id       = Column(UUID(as_uuid=True), nullable=True)
    moderation_notes   = Column(Text, nullable=True)  # mandatory when status → COMPLETE

    status             = Column(
        Enum(ModerationStatus, native_enum=False),
        nullable=False,
        default=ModerationStatus.PENDING,
    )
    completed_at       = Column(DateTime(timezone=True), nullable=True)
    created_at         = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    script = relationship("ScannedScript", back_populates="moderation_review")


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


# ---------------------------------------------------------------------------
# ExamBoardSession — M09.4 Board Approval Gate (paper-level, post BOARD_FINALISED)
# ---------------------------------------------------------------------------

class ExamBoardSession(Base):
    """
    Examination Board session for approving results of one exam paper.

    Created by Dean/Admin after all scripts are BOARD_FINALISED.
    Board reviews aggregate statistics (mean, pass rate) and casts approve/reject.

    Human-gate invariants (M09.4):
      status → APPROVED only via board approve endpoint.
      status → REJECTED only via board reject endpoint.
      status → DECLARED only via admin declare endpoint.
      After APPROVED: no mark adjustments permitted (service-enforced).
    """
    __tablename__ = "exam_board_sessions"
    __table_args__ = (
        Index("ix_board_sessions_exam_paper", "exam_paper_id"),
        Index("ix_board_sessions_status",     "status"),
        Index("ix_board_sessions_convened_by", "convened_by"),
        Index("ix_board_sessions_created_at", "created_at"),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_paper_id    = Column(UUID(as_uuid=True), nullable=False)
    session_title    = Column(Text, nullable=False)
    convened_by      = Column(UUID(as_uuid=True), nullable=False)  # DEAN user_id
    convened_at      = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    status           = Column(String(20), nullable=False, server_default="OPEN", default="OPEN")
    board_remarks    = Column(Text, nullable=True)
    decided_by       = Column(UUID(as_uuid=True), nullable=True)
    decided_at       = Column(DateTime(timezone=True), nullable=True)
    declared_by      = Column(UUID(as_uuid=True), nullable=True)
    declared_at      = Column(DateTime(timezone=True), nullable=True)
    created_at       = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    course_approval  = relationship(
        "ExamBoardCourseApproval",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ExamBoardCourseApproval(Base):
    """
    Aggregate statistics snapshot for one exam paper within a board session.

    Stats are computed at session creation from exam_score_ledger entries.
    Stores mean, pass/fail counts, and approval status per course.
    """
    __tablename__ = "exam_board_course_approvals"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_board_course_approval_session"),
        Index("ix_board_course_approvals_session",    "session_id"),
        Index("ix_board_course_approvals_exam_paper", "exam_paper_id"),
        Index("ix_board_course_approvals_status",     "approval_status"),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id       = Column(
        UUID(as_uuid=True),
        ForeignKey("exam_board_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    exam_paper_id    = Column(UUID(as_uuid=True), nullable=False)  # denorm
    mean_marks       = Column(Numeric(6, 2), nullable=True)
    max_marks        = Column(Numeric(6, 2), nullable=True)
    pass_count       = Column(Integer, nullable=True)
    fail_count       = Column(Integer, nullable=True)
    total_scripts    = Column(Integer, nullable=True)
    pass_rate_pct    = Column(Numeric(5, 2), nullable=True)
    approval_status  = Column(
        String(20), nullable=False, server_default="PENDING", default="PENDING"
    )
    created_at       = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    session = relationship("ExamBoardSession", back_populates="course_approval")


# ---------------------------------------------------------------------------
# Revaluation Workflow — M09.3
# ---------------------------------------------------------------------------

class RevaluationStatus(str, enum.Enum):
    """Lifecycle of a revaluation request."""
    SUBMITTED         = "SUBMITTED"          # student submitted
    ACCEPTED          = "ACCEPTED"           # Admin accepted; evaluator assigned
    IN_PROGRESS       = "IN_PROGRESS"        # revaluator working
    EVALUATED         = "EVALUATED"          # revaluator submitted marks
    BOARD_REVIEW      = "BOARD_REVIEW"       # forwarded to Board for ratification
    APPROVED          = "APPROVED"           # Board ratified; awarded_total computed
    REJECTED_BY_BOARD = "REJECTED_BY_BOARD"  # Board rejected the revaluation outcome
    REJECTED          = "REJECTED"           # Admin rejected at intake
    CLOSED            = "CLOSED"             # terminal state


class RevaluationRequest(Base):
    """
    Student revaluation request for a script.

    Human-gate invariants (M09.3):
      - Only DECLARED scripts may have requests (checked in service).
      - assigned_evaluator_id must differ from original + second evaluator.
      - awarded_total = max(original_total, revaluation_total) — never less.
      - Board ratification required before updating exam_score_ledger.
      - This is the ONLY legitimate post-publication mark change path.
    """
    __tablename__ = "sis_revaluation_requests"
    __table_args__ = (
        Index("ix_reval_requests_script",    "script_id"),
        Index("ix_reval_requests_student",   "student_user_id"),
        Index("ix_reval_requests_exam_paper", "exam_paper_id"),
        Index("ix_reval_requests_status",    "status"),
        Index("ix_reval_requests_evaluator", "assigned_evaluator_id"),
        Index("ix_reval_requests_created",   "created_at"),
    )

    id                    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    script_id             = Column(
        UUID(as_uuid=True),
        ForeignKey("scanned_scripts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    exam_paper_id         = Column(UUID(as_uuid=True), nullable=False)  # denorm
    student_user_id       = Column(UUID(as_uuid=True), nullable=False)
    student_roll_ref      = Column(String, nullable=True)
    original_total        = Column(Numeric(6, 2), nullable=False)  # snapshot at request time
    max_marks             = Column(Numeric(6, 2), nullable=False)
    reason                = Column(Text, nullable=False)
    payment_reference     = Column(String, nullable=True)
    status                = Column(String(30), nullable=False, server_default="SUBMITTED", default="SUBMITTED")
    assigned_evaluator_id = Column(UUID(as_uuid=True), nullable=True)
    revaluation_total     = Column(Numeric(6, 2), nullable=True)
    awarded_total         = Column(Numeric(6, 2), nullable=True)  # max(original, revaluation)
    admin_notes           = Column(Text, nullable=True)
    board_remarks         = Column(Text, nullable=True)
    decided_by            = Column(UUID(as_uuid=True), nullable=True)
    decided_at            = Column(DateTime(timezone=True), nullable=True)
    window_closes_at      = Column(DateTime(timezone=True), nullable=True)
    created_at            = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at            = Column(
        DateTime(timezone=True), nullable=True, onupdate=text("now()")
    )

    evaluations = relationship(
        "RevaluationEvaluation",
        back_populates="request",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# Digital Exams — M09.5
# ---------------------------------------------------------------------------

class DigitalExamSessionStatus(str, enum.Enum):
    DRAFT  = "DRAFT"   # created; not yet open to students
    ACTIVE = "ACTIVE"  # students can start attempts
    CLOSED = "CLOSED"  # no new attempts; scoring complete


class DigitalAttemptStatus(str, enum.Enum):
    IN_PROGRESS     = "IN_PROGRESS"     # student started; timer running
    SUBMITTED       = "SUBMITTED"       # student submitted; awaiting auto-score
    SCORED          = "SCORED"          # MCQ auto-scored; subjective pending evaluator
    FULLY_EVALUATED = "FULLY_EVALUATED" # all subjective scored and submitted by faculty


class DigitalExamSession(Base):
    """
    One digital exam delivery window for an exam paper.

    Human-gate invariants (M09.5):
      status → ACTIVE only via admin activate endpoint.
      status → CLOSED only via admin close endpoint.
      Students can only start attempts while status == ACTIVE.
    """
    __tablename__ = "digital_exam_sessions"
    __table_args__ = (
        Index("ix_digital_sessions_paper",   "exam_paper_id"),
        Index("ix_digital_sessions_status",  "status"),
        Index("ix_digital_sessions_created", "created_at"),
    )

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_paper_id     = Column(UUID(as_uuid=True), nullable=False)
    created_by        = Column(UUID(as_uuid=True), nullable=False)
    title             = Column(String, nullable=False)
    status            = Column(
        Enum(DigitalExamSessionStatus, native_enum=False),
        nullable=False,
        default=DigitalExamSessionStatus.DRAFT,
    )
    window_start      = Column(DateTime(timezone=True), nullable=True)
    window_end        = Column(DateTime(timezone=True), nullable=True)
    max_duration_mins = Column(Integer, nullable=False, default=180)
    instructions      = Column(Text, nullable=True)
    activated_at      = Column(DateTime(timezone=True), nullable=True)
    closed_at         = Column(DateTime(timezone=True), nullable=True)
    created_at        = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    attempts = relationship(
        "DigitalExamAttempt",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class DigitalExamAttempt(Base):
    """
    One attempt per student per digital exam session.

    Human-gate invariants (M09.5):
      status → SUBMITTED only via student submit endpoint.
      status → SCORED by system after auto-scoring MCQ responses.
      One attempt per student per session (enforced by UNIQUE constraint).
      auto_score covers MCQ questions only; subjective marks pending evaluator.
    """
    __tablename__ = "digital_exam_attempts"
    __table_args__ = (
        UniqueConstraint("session_id", "student_user_id", name="uq_digital_attempt_session_student"),
        Index("ix_digital_attempts_session",  "session_id"),
        Index("ix_digital_attempts_student",  "student_user_id"),
        Index("ix_digital_attempts_status",   "status"),
        Index("ix_digital_attempts_submitted", "submitted_at"),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id       = Column(
        UUID(as_uuid=True),
        ForeignKey("digital_exam_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_user_id  = Column(UUID(as_uuid=True), nullable=False)
    status           = Column(
        Enum(DigitalAttemptStatus, native_enum=False),
        nullable=False,
        default=DigitalAttemptStatus.IN_PROGRESS,
    )
    started_at       = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    expires_at       = Column(DateTime(timezone=True), nullable=True)
    submitted_at     = Column(DateTime(timezone=True), nullable=True)
    auto_scored_at   = Column(DateTime(timezone=True), nullable=True)
    # MCQ auto-score (sum of correct MCQ marks); null until SCORED
    auto_score       = Column(Numeric(6, 2), nullable=True)
    # Sum of all question marks in the paper (denominator for MCQ section)
    mcq_max_score    = Column(Numeric(6, 2), nullable=True)
    created_at       = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    session = relationship("DigitalExamSession", back_populates="attempts")
    responses = relationship(
        "DigitalExamResponse",
        back_populates="attempt",
        cascade="all, delete-orphan",
    )


class DigitalExamResponse(Base):
    """
    One response row per question per digital exam attempt.

    MCQ questions: selected_option + is_auto_scored + auto_score set on submit.
    Subjective questions: response_text; auto_score remains NULL.
    One response per (attempt_id, question_id) enforced by UNIQUE constraint.
    """
    __tablename__ = "digital_exam_responses"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_digital_response_attempt_question"),
        Index("ix_digital_responses_attempt",  "attempt_id"),
        Index("ix_digital_responses_question", "question_id"),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id       = Column(
        UUID(as_uuid=True),
        ForeignKey("digital_exam_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id      = Column(UUID(as_uuid=True), nullable=False)
    question_type    = Column(String(30), nullable=True)
    # MCQ response
    selected_option  = Column(String(4), nullable=True)
    # Subjective response
    response_text    = Column(Text, nullable=True)
    # Auto-scoring (MCQ only)
    is_auto_scored   = Column(Boolean, nullable=False, default=False, server_default="false")
    auto_score       = Column(Numeric(6, 2), nullable=True)
    is_correct       = Column(Boolean, nullable=True)
    # Faculty scoring (subjective only — M09.5 Phase D)
    faculty_score    = Column(Numeric(6, 2), nullable=True)
    faculty_note     = Column(Text, nullable=True)
    faculty_scored_by = Column(UUID(as_uuid=True), nullable=True)
    faculty_scored_at = Column(DateTime(timezone=True), nullable=True)
    answered_at      = Column(DateTime(timezone=True), nullable=True)
    updated_at       = Column(DateTime(timezone=True), nullable=True)
    created_at       = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    attempt = relationship("DigitalExamAttempt", back_populates="responses")


class RevaluationEvaluation(Base):
    """Per-question marks from the revaluation evaluator."""
    __tablename__ = "sis_revaluation_evaluations"
    __table_args__ = (
        Index("ix_reval_evals_request",  "request_id"),
        Index("ix_reval_evals_question", "question_id"),
    )

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id         = Column(
        UUID(as_uuid=True),
        ForeignKey("sis_revaluation_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id        = Column(UUID(as_uuid=True), nullable=False)
    question_type      = Column(String(30), nullable=True)
    max_marks          = Column(Numeric(6, 2), nullable=True)
    original_marks     = Column(Numeric(6, 2), nullable=True)
    revaluation_marks  = Column(Numeric(6, 2), nullable=True)
    evaluator_note     = Column(Text, nullable=True)
    created_at         = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    request = relationship("RevaluationRequest", back_populates="evaluations")
