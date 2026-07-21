"""
M04 Assignments — SQLAlchemy models.

Tables (all tenant-schema, not public):
  assignments             — faculty-created theory/coursework assignments
  assignment_submissions  — student submissions per assignment (supports attempts)

Kept fully separate from m06_labs_evaluator (Labs = practical/code work with an
AI-evaluation pipeline). Assignments here are manually graded by faculty only —
no rubric/AI-score/plagiarism pipeline, no eval Celery job. "AI advises, humans
decide" is trivially satisfied because no AI is involved in grading at all.

Tenant isolation: all tables live in the tenant schema (no schema= kwarg).
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey, Index,
    Integer, Numeric, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AssignmentType(str, enum.Enum):
    ESSAY       = "ESSAY"
    CASE_STUDY  = "CASE_STUDY"
    REPORT      = "REPORT"
    HOMEWORK    = "HOMEWORK"
    OTHER       = "OTHER"


class AssignmentStatus(str, enum.Enum):
    """Lifecycle of one coursework assignment.

        DRAFT      faculty is still writing it.
        PUBLISHED  students can see it and submit.
        CLOSED     the window has shut; no more student submissions.
        SUBMITTED  faculty has handed it to the department for evaluation, which
                   is what lets Admin/Dean allocate an Evaluator per submission.
        FINALIZED  a human (Dean) has ratified the marks. Grading is closed, but
                   the marks are NOT yet visible to students.
        RELEASED   the ratified marks have been released to students, who can now
                   see their results. Reached only by an explicit human action.
        ARCHIVED   filed away (from FINALIZED or RELEASED); restorable.
    """
    DRAFT     = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CLOSED    = "CLOSED"
    SUBMITTED = "SUBMITTED"
    FINALIZED = "FINALIZED"
    RELEASED  = "RELEASED"
    ARCHIVED  = "ARCHIVED"


class SubmissionStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    GRADED    = "GRADED"
    RETURNED  = "RETURNED"


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------

class Assignment(Base):
    """
    One coursework assignment published by faculty (essay/case study/report/
    homework/PDF/Word submission). Contributes to Internal Assessment via
    faculty-set weightage_percent (informational display this phase — no
    automatic sync into sis_marks_components/sis_marks_entries).
    """
    __tablename__ = "assignments"
    __table_args__ = (
        Index("ix_assignments_syllabus",   "syllabus_id"),
        Index("ix_assignments_created_by", "created_by_user_id"),
        Index("ix_assignments_status",     "status"),
    )

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    syllabus_id          = Column(
        UUID(as_uuid=True),
        ForeignKey("syllabi.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id   = Column(UUID(as_uuid=True), nullable=False)

    title                = Column(String, nullable=False)
    description          = Column(Text, nullable=True)
    instructions         = Column(Text, nullable=True)
    assignment_type      = Column(
        Enum(AssignmentType, native_enum=False),
        nullable=False,
        default=AssignmentType.HOMEWORK,
    )

    max_marks            = Column(Numeric(6, 2), nullable=False)
    # Faculty-set weightage toward Internal Assessment (informational display
    # this phase — no automatic sync into sis_marks_components/entries).
    weightage_percent    = Column(Numeric(5, 2), nullable=True)

    # The actual questions the faculty set, in order. Each item is
    # {question_number, question_text, marks, notes}. Empty [] = no structured
    # questions (either the faculty uploaded a question paper instead, or this is
    # an older metadata-only assignment). When non-empty, the marks sum to
    # max_marks (enforced in the service). JSONB so the whole builder round-trips
    # as one column without a child table.
    questions            = Column(JSONB, nullable=False, server_default="[]")
    # S3 object key of an uploaded question paper (.pdf/.docx), used as the
    # fallback when the faculty did not enter structured questions. NULL = none.
    question_paper_url   = Column(String, nullable=True)

    due_date             = Column(DateTime(timezone=True), nullable=True)
    allow_late           = Column(Boolean, nullable=False, default=True)
    late_penalty_percent = Column(Numeric(5, 2), nullable=True)

    max_attempts         = Column(Integer, nullable=False, default=1)
    # e.g. ["pdf","docx","doc"] — null/empty = any type allowed
    allowed_file_types   = Column(JSONB, nullable=False, server_default="[]")

    status               = Column(
        Enum(AssignmentStatus, native_enum=False),
        nullable=False,
        default=AssignmentStatus.DRAFT,
    )
    published_at         = Column(DateTime(timezone=True), nullable=True)
    closed_at            = Column(DateTime(timezone=True), nullable=True)

    # The evaluator(s) the faculty nominated when creating the assignment. Each
    # student submission becomes one work item against these, round-robin, through
    # the M09.6 assignment engine — this column is the nomination, never a second
    # allocation ledger. NULL/[] = nobody nominated, and the department allocates
    # by hand exactly as before.
    evaluator_user_ids     = Column(JSONB, nullable=True)

    # Faculty hands the closed assignment to the department for evaluation.
    submitted_at           = Column(DateTime(timezone=True), nullable=True)
    submitted_by_user_id   = Column(UUID(as_uuid=True), nullable=True)

    # The human ratification of the marks, recorded at the database level and not
    # only in the UI: nothing computes or infers this, a person does it, and
    # grading stops once it is set.
    finalized_at           = Column(DateTime(timezone=True), nullable=True)
    finalized_by_user_id   = Column(UUID(as_uuid=True), nullable=True)

    created_at           = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at           = Column(DateTime(timezone=True), nullable=True)

    submissions = relationship(
        "AssignmentSubmission",
        back_populates="assignment",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# AssignmentSubmission
# ---------------------------------------------------------------------------

class AssignmentSubmission(Base):
    """
    One student submission (attempt) for an assignment.

    content_url: S3 object key for file uploads (PDF/DOCX/etc.)
    content_text: inline text (mutually exclusive with content_url in practice)

    Multiple attempts (if assignment.max_attempts > 1) are separate rows,
    distinguished by attempt_number — this is the "submission history".
    """
    __tablename__ = "assignment_submissions"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id", "student_user_id", "attempt_number",
            name="uq_assignment_submissions_attempt",
        ),
        Index("ix_assignment_submissions_assignment",         "assignment_id"),
        Index("ix_assignment_submissions_student",            "student_user_id"),
        Index("ix_assignment_submissions_assignment_student", "assignment_id", "student_user_id"),
        Index("ix_assignment_submissions_status",             "status"),
    )

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id      = Column(
        UUID(as_uuid=True),
        ForeignKey("assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_user_id    = Column(UUID(as_uuid=True), nullable=False)
    attempt_number     = Column(Integer, nullable=False, default=1)

    content_url        = Column(String, nullable=True)
    content_text       = Column(Text, nullable=True)

    submitted_at       = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    is_late            = Column(Boolean, nullable=False, default=False)

    status             = Column(
        Enum(SubmissionStatus, native_enum=False),
        nullable=False,
        default=SubmissionStatus.SUBMITTED,
    )
    # The AUTHORITATIVE final grade. The assignment's owning faculty is the
    # academic authority: an evaluator's save lands here as their recommendation
    # standing unchallenged, and the faculty's review overwrites it.
    marks_obtained     = Column(Numeric(6, 2), nullable=True)
    feedback           = Column(Text, nullable=True)

    # What the EVALUATOR recommended, preserved permanently. Written once per
    # evaluator save and never touched by the faculty review, so the
    # recommendation and the final decision can always be compared — and the
    # faculty adjusting a mark can no longer destroy the evaluator's number.
    # NULL on rows graded before this distinction existed, and on assignments the
    # owning faculty graded themselves (there was no separate recommendation).
    evaluator_marks_obtained = Column(Numeric(6, 2), nullable=True)
    evaluator_feedback       = Column(Text, nullable=True)

    graded_by_user_id  = Column(UUID(as_uuid=True), nullable=True)
    graded_at          = Column(DateTime(timezone=True), nullable=True)
    returned_at        = Column(DateTime(timezone=True), nullable=True)

    assignment = relationship("Assignment", back_populates="submissions")
    ai_evaluation = relationship(
        "AssignmentEvaluation",
        back_populates="submission",
        uselist=False,
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# AssignmentEvaluation — the AI's ADVISORY analysis of one submission.
# ---------------------------------------------------------------------------

class AIEvalStatus(str, enum.Enum):
    """Lifecycle of the background AI evaluation for one submission.

        PENDING     enqueued, not started.
        EXTRACTING  downloading + extracting text from the uploaded file.
        EVALUATING  the LLM is scoring the submission.
        COMPLETED   results stored; the evaluator can see them.
        FAILED      something went wrong; error_log explains it. The submission
                    and manual grading are UNAFFECTED — this row is advisory only.
    """
    PENDING    = "PENDING"
    EXTRACTING = "EXTRACTING"
    EVALUATING = "EVALUATING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"


class AssignmentEvaluation(Base):
    """AI-generated, ADVISORY evaluation of a single coursework submission.

    Kept in its own table (never on assignment_submissions) so the human's marks
    and the AI's suggestions never share a column: the evaluator's marks live on
    the submission and are authoritative; nothing here is ever copied into them
    automatically. "AI advises, humans decide" is structural, not a convention.

    One row per submission (unique). Written only by the background worker.
    """
    __tablename__ = "assignment_evaluations"
    __table_args__ = (
        Index("ix_assignment_evaluations_submission", "submission_id"),
        Index("ix_assignment_evaluations_status",     "status"),
    )

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assignment_submissions.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )

    status = Column(
        Enum(AIEvalStatus, native_enum=False),
        nullable=False, default=AIEvalStatus.PENDING, server_default="PENDING",
    )

    # --- Submission summary (Phase: file processing) ---
    extracted_text = Column(Text, nullable=True)
    word_count     = Column(Integer, nullable=True)
    file_type      = Column(String, nullable=True)

    # --- Suggested marks (advisory) ---
    # suggested_marks JSONB: [{question_number, suggested, max, reason}]
    suggested_marks         = Column(JSONB, nullable=True)
    overall_suggested_marks = Column(Numeric(6, 2), nullable=True)
    percentage              = Column(Numeric(5, 2), nullable=True)
    confidence_level        = Column(String, nullable=True)  # HIGH | MEDIUM | LOW

    # --- Structured feedback JSONB ---
    # {strengths[], weaknesses[], missing_concepts[], writing_quality,
    #  technical_correctness, suggestions[]}
    feedback = Column(JSONB, nullable=True)

    # --- Rubric evaluation JSONB: [{criterion, score, max, comment}] ---
    rubric_scores = Column(JSONB, nullable=True)

    # --- Bloom's analysis JSONB (advisory): {expected_level, detected_level,
    #     alignment_percent, notes} ---
    bloom_analysis = Column(JSONB, nullable=True)

    # --- CO analysis JSONB (advisory): {covered[], weak[], missing[], notes} ---
    co_analysis = Column(JSONB, nullable=True)

    # --- Internal similarity (same-assignment cohort) ---
    similarity_score   = Column(Float, nullable=True)   # 0..1 max cosine
    similarity_matches = Column(JSONB, nullable=True)   # top-k [{submission_id, similarity}]
    # No external/web plagiarism engine exists — never fabricate a score.
    plagiarism_status  = Column(String, nullable=False, server_default="PLACEHOLDER")

    # --- Reliability / reproducibility ---
    ai_model      = Column(String, nullable=True)   # the model_used
    # Which provider actually produced the result, and the fallback path taken,
    # e.g. provider_used="groq", fallback_chain="gemini→groq".
    provider_used  = Column(String, nullable=True)
    fallback_chain = Column(String, nullable=True)
    prompt_hash   = Column(String, nullable=True)
    processing_ms = Column(Integer, nullable=True)
    error_log     = Column(Text, nullable=True)
    retry_count   = Column(Integer, nullable=False, server_default="0", default=0)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=text("now()"))

    submission = relationship("AssignmentSubmission", back_populates="ai_evaluation")
