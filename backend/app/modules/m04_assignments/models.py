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
    Boolean, Column, DateTime, Enum, ForeignKey, Index,
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
        FINALIZED  a human has ratified the marks. Terminal for grading.
        ARCHIVED   filed away.
    """
    DRAFT     = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CLOSED    = "CLOSED"
    SUBMITTED = "SUBMITTED"
    FINALIZED = "FINALIZED"
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
    marks_obtained     = Column(Numeric(6, 2), nullable=True)
    feedback           = Column(Text, nullable=True)
    graded_by_user_id  = Column(UUID(as_uuid=True), nullable=True)
    graded_at          = Column(DateTime(timezone=True), nullable=True)
    returned_at        = Column(DateTime(timezone=True), nullable=True)

    assignment = relationship("Assignment", back_populates="submissions")
