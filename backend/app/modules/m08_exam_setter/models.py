"""
M08 Exam Setter — SQLAlchemy models.

Tables (all tenant-schema, no schema= kwarg):
  exam_papers              — faculty-configured exam papers
  exam_questions           — AI-generated questions per paper
  blooms_compliance_reports — Bloom's level distribution analysis per paper

Human-gate invariants:
  exam_papers.status → SUBMITTED only via faculty submit endpoint (Gate 1).
  exam_papers.status → BOARD_APPROVED / BOARD_RETURNED only via board decision endpoint (Gate 2).
  exam_papers.status → SEALED only via faculty seal endpoint (Gate 3).
  exam_papers.status → RELEASED only via Celery release task (timed auto-release).
  No Celery task ever sets status beyond GENERATED.
  Model answers are never accessible when status == SEALED.

Tenant isolation: all tables live in the tenant schema.
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

class ExamType(str, enum.Enum):
    MID_SEM  = "MID_SEM"
    END_SEM  = "END_SEM"
    QUIZ     = "QUIZ"
    INTERNAL = "INTERNAL"
    CUSTOM   = "CUSTOM"


class ExamPaperStatus(str, enum.Enum):
    DRAFT          = "DRAFT"           # initial record created
    GENERATING     = "GENERATING"      # Celery job running
    GENERATED      = "GENERATED"       # questions written; faculty can edit
    SUBMITTED      = "SUBMITTED"       # Gate 1: faculty submitted for Board review
    BOARD_APPROVED = "BOARD_APPROVED"  # Gate 2: Board approved; faculty can seal
    BOARD_RETURNED = "BOARD_RETURNED"  # Gate 2 return: Board returned with comments
    SEALED         = "SEALED"          # Gate 3: encrypted; inaccessible until release
    RELEASED       = "RELEASED"        # auto-decrypted at release_at


class QuestionType(str, enum.Enum):
    MCQ             = "MCQ"
    SHORT_ANSWER    = "SHORT_ANSWER"
    LONG_ANSWER     = "LONG_ANSWER"
    PROBLEM_SOLVING = "PROBLEM_SOLVING"


class BloomLevel(str, enum.Enum):
    REMEMBER   = "REMEMBER"
    UNDERSTAND = "UNDERSTAND"
    APPLY      = "APPLY"
    ANALYSE    = "ANALYSE"
    EVALUATE   = "EVALUATE"
    CREATE     = "CREATE"


# ---------------------------------------------------------------------------
# ExamPaper
# ---------------------------------------------------------------------------

class ExamPaper(Base):
    """
    One exam paper configuration created by faculty.

    requested_dist / actual_dist JSONB schema:
      {remember: float, understand: float, apply: float,
       analyse: float, evaluate: float, create: float}
      Values are percentages (0–100), must sum to 100.

    question_format JSONB schema:
      {mcq_count: int, short_count: int, long_count: int, problem_count: int}

    units_included JSONB schema:
      [1, 2, 3]   — unit numbers from the linked syllabus

    Human-gate: status advances to SUBMITTED / BOARD_APPROVED / BOARD_RETURNED
    / SEALED only via explicit human endpoints.
    Celery task writes only up to GENERATED.
    No Celery task ever reads exam content while status == SEALED.
    """
    __tablename__ = "exam_papers"
    __table_args__ = (
        Index("ix_exam_papers_course",    "course_id"),
        Index("ix_exam_papers_creator",   "created_by"),
        Index("ix_exam_papers_status",    "status"),
        Index("ix_exam_papers_created",   "created_at"),
        Index("ix_exam_papers_release",   "release_at"),
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Linked to M02 course / syllabus
    course_id           = Column(UUID(as_uuid=True), nullable=False)

    # Faculty who created this paper
    created_by          = Column(UUID(as_uuid=True), nullable=False)

    title               = Column(String, nullable=False)
    exam_type           = Column(
        Enum(ExamType, native_enum=False),
        nullable=False,
        default=ExamType.END_SEM,
    )
    total_marks         = Column(Integer, nullable=False, default=100)
    duration_mins       = Column(Integer, nullable=False, default=180)

    # Which units from the syllabus to cover
    units_included      = Column(JSONB, nullable=False, server_default="[]")

    # Requested question format counts
    question_format     = Column(JSONB, nullable=False, server_default="{}")

    # Bloom's level distribution: {remember:%, understand:%, ...}
    requested_dist      = Column(JSONB, nullable=False, server_default="{}")

    # Computed after generation
    actual_dist         = Column(JSONB, nullable=True)

    special_instructions = Column(Text, nullable=True)

    # AI provenance
    ai_model            = Column(String, nullable=True)
    prompt_hash         = Column(String, nullable=True)

    # FK to public.task_jobs for generation Celery task
    generation_job_id   = Column(UUID(as_uuid=True), nullable=True)

    # Workflow status
    status              = Column(
        Enum(ExamPaperStatus, native_enum=False),
        nullable=False,
        default=ExamPaperStatus.DRAFT,
    )

    # Gate 1: faculty submits for Board review
    submitted_at        = Column(DateTime(timezone=True), nullable=True)

    # Gate 2: Board decision — written ONLY by board decision endpoint
    approved_by         = Column(UUID(as_uuid=True), nullable=True)
    approved_at         = Column(DateTime(timezone=True), nullable=True)
    board_comment       = Column(Text, nullable=True)

    # Gate 3: faculty seals paper — written ONLY by seal endpoint
    sealed_at           = Column(DateTime(timezone=True), nullable=True)
    release_at          = Column(DateTime(timezone=True), nullable=True)

    # S3 object key where encrypted paper blob is stored (NOT the crypto key)
    encrypted_blob_key  = Column(String, nullable=True)

    # Reference to KMS key / env var name — never the key itself
    encryption_key_ref  = Column(String, nullable=True)

    # Auto-release Celery task job id (ETA task)
    release_job_id      = Column(UUID(as_uuid=True), nullable=True)

    # Written by release Celery task only
    released_at         = Column(DateTime(timezone=True), nullable=True)

    created_at          = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at          = Column(DateTime(timezone=True), nullable=True)

    questions = relationship(
        "ExamQuestion",
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="ExamQuestion.created_at",
    )
    blooms_report = relationship(
        "BloomsComplianceReport",
        back_populates="paper",
        uselist=False,
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# ExamQuestion
# ---------------------------------------------------------------------------

class ExamQuestion(Base):
    """
    One question within an exam paper.

    options JSONB schema (MCQ only):
      [{label: "A", text: "..."}, {label: "B", text: "..."}, ...]

    marking_scheme JSONB schema:
      [{criterion: str, marks: float, description: str}, ...]

    set_membership JSONB schema:
      ["A", "B"]  — which sets include this question
      ["A"]       — Set A only

    Human-gate: questions are created by Celery generate_exam_paper task.
    Faculty can edit (is_edited=True) or replace (new question inserted).
    Questions are NOT readable through the API when paper status == SEALED.
    """
    __tablename__ = "exam_questions"
    __table_args__ = (
        Index("ix_exam_questions_paper",  "exam_paper_id"),
        Index("ix_exam_questions_bloom",  "bloom_level"),
        Index("ix_exam_questions_type",   "question_type"),
        Index("ix_exam_questions_unit",   "unit_number"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_paper_id   = Column(
        UUID(as_uuid=True),
        ForeignKey("exam_papers.id", ondelete="CASCADE"),
        nullable=False,
    )

    unit_number     = Column(Integer, nullable=False)

    # Denormalized CO code for display (e.g. "CO1")
    co_code         = Column(String, nullable=True)

    bloom_level     = Column(
        Enum(BloomLevel, native_enum=False),
        nullable=False,
    )
    question_type   = Column(
        Enum(QuestionType, native_enum=False),
        nullable=False,
    )

    question_text   = Column(Text, nullable=False)

    # [{label:"A", text:"..."}, ...] — MCQ only
    options         = Column(JSONB, nullable=True)

    # "A", "B", etc. — MCQ correct option label
    correct_option  = Column(String, nullable=True)

    marks           = Column(Numeric(5, 1), nullable=False)

    # Model answer — NOT exposed via API when status == SEALED
    model_answer    = Column(Text, nullable=True)

    # [{criterion, marks, description}]
    marking_scheme  = Column(JSONB, nullable=True)

    # Which sets contain this question: ["A","B"] or ["A"] or ["B"]
    set_membership  = Column(JSONB, nullable=False, server_default='["A","B"]')

    # Provenance
    ai_generated    = Column(Boolean, nullable=False, default=True)
    is_edited       = Column(Boolean, nullable=False, default=False)

    created_at      = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at      = Column(DateTime(timezone=True), nullable=True)

    paper = relationship("ExamPaper", back_populates="questions")


# ---------------------------------------------------------------------------
# BloomsComplianceReport
# ---------------------------------------------------------------------------

class BloomsComplianceReport(Base):
    """
    One compliance report per exam paper (1:1 with ExamPaper).
    Written by generate_exam_paper Celery task; never updated by human action.

    violations JSONB schema:
      [{level: str, requested_pct: float, actual_pct: float, delta_pct: float}]
    """
    __tablename__ = "blooms_compliance_reports"
    __table_args__ = (
        UniqueConstraint("exam_paper_id", name="uq_blooms_report_paper"),
        Index("ix_blooms_report_paper", "exam_paper_id"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_paper_id   = Column(
        UUID(as_uuid=True),
        ForeignKey("exam_papers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    requested_dist  = Column(JSONB, nullable=False)
    actual_dist     = Column(JSONB, nullable=False)
    compliance_ok   = Column(Boolean, nullable=False, default=False)

    # [{level, requested_pct, actual_pct, delta_pct}]
    violations      = Column(JSONB, nullable=False, server_default="[]")

    generated_at    = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    paper = relationship("ExamPaper", back_populates="blooms_report")
