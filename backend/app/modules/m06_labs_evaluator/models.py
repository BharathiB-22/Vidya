"""
M06 Labs & Assignment Evaluator — SQLAlchemy models.

Tables (all tenant-schema, not public):
  lab_assignments   — faculty-created assignments (WRITTEN or CODE)
  lab_submissions   — student submissions per assignment
  lab_evaluations   — AI evaluation result per submission (1:1)
  grade_ledger      — append-only ratified marks (written only on faculty ratify)

Tenant isolation: all tables live in the tenant schema (no schema= kwarg).

Human-gate invariant:
  grade_ledger rows are NEVER written by any Celery task.
  Only POST /submissions/{id}/ratify writes to grade_ledger.
  No UPDATE or DELETE on grade_ledger ever.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float,
    ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SubmissionType(str, enum.Enum):
    WRITTEN = "WRITTEN"
    CODE    = "CODE"


class AssignmentStatus(str, enum.Enum):
    DRAFT     = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CLOSED    = "CLOSED"
    ARCHIVED  = "ARCHIVED"


class AIScanStatus(str, enum.Enum):
    PENDING = "PENDING"
    CLEAN   = "CLEAN"
    FLAGGED = "FLAGGED"


class SubmissionStatus(str, enum.Enum):
    SUBMITTED  = "SUBMITTED"
    EVALUATING = "EVALUATING"
    EVALUATED  = "EVALUATED"
    REVIEWED   = "REVIEWED"   # faculty opened review panel
    RATIFIED   = "RATIFIED"   # marks written to grade_ledger


class ConfidenceLevel(str, enum.Enum):
    HIGH   = "HIGH"    # all criterion variance < 10 %
    MEDIUM = "MEDIUM"
    LOW    = "LOW"     # any criterion variance > 25 %


# ---------------------------------------------------------------------------
# LabAssignment
# ---------------------------------------------------------------------------

class LabAssignment(Base):
    """
    One assignment published by faculty.

    Optionally linked to an M03 KitAssignment (kit_assignment_id is the
    kit_assignments.id UUID, assignment_number identifies which item within
    that kit was used as the template).  Both fields are nullable — faculty
    can create standalone assignments without a kit source.

    rubric JSONB schema:
      [{criterion_id: str, name: str, description: str,
        max_marks: int, weight: float (0–1)}]
      weights must sum to 1.0; validated in service layer.

    test_cases JSONB schema (CODE only):
      [{id: str, name: str, stdin: str, expected_stdout: str,
        is_hidden: bool, points: int}]
      Hidden test cases are NEVER returned to students.
    """
    __tablename__ = "lab_assignments"
    __table_args__ = (
        Index("ix_lab_assignments_syllabus",       "syllabus_id"),
        Index("ix_lab_assignments_created_by",     "created_by_user_id"),
        Index("ix_lab_assignments_status",         "status"),
        Index("ix_lab_assignments_submission_type", "submission_type"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Optional link to M02 syllabus for context
    syllabus_id         = Column(
        UUID(as_uuid=True),
        ForeignKey("syllabi.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Optional link to M03 KitAssignment used as template
    kit_assignment_id   = Column(UUID(as_uuid=True), nullable=True)
    created_by_user_id  = Column(UUID(as_uuid=True), nullable=False)

    title               = Column(String, nullable=False)
    description         = Column(Text, nullable=True)
    submission_type     = Column(
        Enum(SubmissionType, native_enum=False),
        nullable=False,
        default=SubmissionType.WRITTEN,
    )
    # Programming language (CODE only): "python", "java", etc.
    language            = Column(String, nullable=True)

    # [{criterion_id, name, description, max_marks, weight}]
    rubric              = Column(JSONB, nullable=False, server_default="[]")
    # [{id, name, stdin, expected_stdout, is_hidden, points}] — CODE only
    test_cases          = Column(JSONB, nullable=False, server_default="[]")

    # Computed from rubric sum(max_marks) on publish; stored for reporting
    max_marks           = Column(Integer, nullable=True)
    deadline            = Column(DateTime(timezone=True), nullable=True)
    ai_not_permitted    = Column(Boolean, nullable=False, default=True)
    allow_late          = Column(Boolean, nullable=False, default=False)
    # Cosine similarity threshold for plagiarism flagging (0–1)
    plagiarism_threshold = Column(Numeric(4, 3), nullable=False, server_default="0.850")

    status              = Column(
        Enum(AssignmentStatus, native_enum=False),
        nullable=False,
        default=AssignmentStatus.DRAFT,
    )
    published_at        = Column(DateTime(timezone=True), nullable=True)
    closed_at           = Column(DateTime(timezone=True), nullable=True)
    created_at          = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at          = Column(DateTime(timezone=True), nullable=True)

    submissions = relationship(
        "LabSubmission",
        back_populates="assignment",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# LabSubmission
# ---------------------------------------------------------------------------

class LabSubmission(Base):
    """
    One student submission per assignment.

    content_url: S3 object key for file uploads (WRITTEN PDF/DOCX or CODE zip)
    content_text: inline text/code (mutually exclusive with content_url in practice;
                  both nullable so the service can handle either path)

    ai_scan_result JSONB schema:
      {probability: float, confidence: float,
       highlights: [{start: int, end: int, score: float}]}
    """
    __tablename__ = "lab_submissions"
    __table_args__ = (
        Index("ix_lab_submissions_assignment",       "assignment_id"),
        Index("ix_lab_submissions_student",          "student_user_id"),
        Index("ix_lab_submissions_assignment_student", "assignment_id", "student_user_id"),
        Index("ix_lab_submissions_status",           "status"),
        Index("ix_lab_submissions_ai_scan_status",   "ai_scan_status"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id       = Column(
        UUID(as_uuid=True),
        ForeignKey("lab_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_user_id     = Column(UUID(as_uuid=True), nullable=False)
    submission_type     = Column(
        Enum(SubmissionType, native_enum=False),
        nullable=False,
    )

    # File upload path in object storage
    content_url         = Column(String, nullable=True)
    # Inline text (WRITTEN) or code (CODE)
    content_text        = Column(Text, nullable=True)

    submitted_at        = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    is_late             = Column(Boolean, nullable=False, default=False)

    # FK to public.task_jobs for the evaluation Celery task
    eval_job_id         = Column(UUID(as_uuid=True), nullable=True)

    # AI content detection result
    ai_scan_result      = Column(JSONB, nullable=True)
    ai_scan_status      = Column(
        Enum(AIScanStatus, native_enum=False),
        nullable=False,
        default=AIScanStatus.PENDING,
    )

    status              = Column(
        Enum(SubmissionStatus, native_enum=False),
        nullable=False,
        default=SubmissionStatus.SUBMITTED,
    )

    assignment  = relationship("LabAssignment", back_populates="submissions")
    evaluation  = relationship(
        "LabEvaluation",
        back_populates="submission",
        uselist=False,
        cascade="all, delete-orphan",
    )
    grade_entry = relationship(
        "GradeLedger",
        back_populates="submission",
        uselist=False,
    )


# ---------------------------------------------------------------------------
# LabEvaluation
# ---------------------------------------------------------------------------

class LabEvaluation(Base):
    """
    AI evaluation result for one submission (1:1 with LabSubmission).

    rubric_scores JSONB schema:
      [{criterion_id: str, ai_score: float, ai_justification: str,
        human_score: float|null, human_note: str|null}]

    test_results JSONB schema (CODE only):
      [{id: str, name: str, passed: bool, actual_stdout: str,
        error: str|null, points_awarded: int}]

    static_analysis JSONB schema (CODE only):
      {complexity_score: int, complexity_label: str,
       issues: [{line: int, message: str, code: str}]}

    plagiarism_matches JSONB schema:
      [{submission_id: str, similarity: float, student_user_id: str}]
      Top-3 matches by similarity. student_user_id is masked until ratified.
    """
    __tablename__ = "lab_evaluations"
    __table_args__ = (
        UniqueConstraint("submission_id", name="uq_lab_evaluations_submission"),
        Index("ix_lab_evaluations_submission", "submission_id"),
        Index("ix_lab_evaluations_confidence", "confidence_level"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id       = Column(
        UUID(as_uuid=True),
        ForeignKey("lab_submissions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Per-criterion AI scores + justifications; human overrides applied here
    rubric_scores       = Column(JSONB, nullable=False, server_default="[]")

    overall_ai_score    = Column(Numeric(6, 2), nullable=True)
    # Null until faculty ratifies or edits; set by ratify endpoint
    overall_human_score = Column(Numeric(6, 2), nullable=True)

    confidence_level    = Column(
        Enum(ConfidenceLevel, native_enum=False),
        nullable=True,
    )

    # CODE evaluation outputs
    test_results        = Column(JSONB, nullable=True)
    static_analysis     = Column(JSONB, nullable=True)

    # Plagiarism
    plagiarism_score    = Column(Float, nullable=True)    # max cosine similarity in cohort
    plagiarism_matches  = Column(JSONB, nullable=True)    # top-3 matches

    # Provenance
    ai_model            = Column(String, nullable=True)
    prompt_hash         = Column(String, nullable=True)

    created_at          = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at          = Column(DateTime(timezone=True), nullable=True)

    submission = relationship("LabSubmission", back_populates="evaluation")


# ---------------------------------------------------------------------------
# GradeLedger  — append-only; no UPDATE or DELETE ever
# ---------------------------------------------------------------------------

class GradeLedger(Base):
    """
    Immutable record of faculty-ratified marks.

    Written once by POST /submissions/{id}/ratify.
    Never updated or deleted — this is the ground truth grade record.

    final_score: the human-ratified mark (may equal overall_ai_score if
                 faculty accepted without edits, but always set explicitly).
    max_marks:   denormalized from LabAssignment at ratification time.
    """
    __tablename__ = "grade_ledger"
    __table_args__ = (
        UniqueConstraint("submission_id", name="uq_grade_ledger_submission"),
        Index("ix_grade_ledger_submission",    "submission_id"),
        Index("ix_grade_ledger_assignment",    "assignment_id"),
        Index("ix_grade_ledger_student",       "student_user_id"),
        Index("ix_grade_ledger_ratified_by",   "ratified_by_user_id"),
        Index("ix_grade_ledger_ratified_at",   "ratified_at"),
    )

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id        = Column(
        UUID(as_uuid=True),
        ForeignKey("lab_submissions.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    # Denormalized for reporting without joining to lab_submissions
    assignment_id        = Column(UUID(as_uuid=True), nullable=False)
    student_user_id      = Column(UUID(as_uuid=True), nullable=False)

    ratified_by_user_id  = Column(UUID(as_uuid=True), nullable=False)
    final_score          = Column(Numeric(6, 2), nullable=False)
    max_marks            = Column(Integer, nullable=False)
    ratification_note    = Column(Text, nullable=True)
    ratified_at          = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    submission = relationship("LabSubmission", back_populates="grade_entry")


# ---------------------------------------------------------------------------
# EvaluatorAssignment — maps an EVALUATOR user to a specific lab assignment
# ---------------------------------------------------------------------------

class EvaluatorAssignment(Base):
    """
    Scoping record: one row per (evaluator, assignment) pair.

    is_active=False soft-deletes the mapping without losing audit history.
    Unique constraint (assignment_id, evaluator_user_id) prevents duplicates.
    """
    __tablename__ = "evaluator_assignments"
    __table_args__ = (
        UniqueConstraint("assignment_id", "evaluator_user_id",
                         name="uq_evaluator_assignment"),
        Index("ix_evaluator_assignments_evaluator", "evaluator_user_id"),
        Index("ix_evaluator_assignments_assignment", "assignment_id"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id       = Column(
        UUID(as_uuid=True),
        ForeignKey("lab_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    evaluator_user_id   = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_by_user_id = Column(UUID(as_uuid=True), nullable=False)
    assigned_at         = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    is_active           = Column(Boolean, nullable=False, default=True)

    assignment = relationship("LabAssignment")
