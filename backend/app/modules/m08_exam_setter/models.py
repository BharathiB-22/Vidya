"""
M08 Exam Setter — SQLAlchemy models.

Tables (all tenant-schema, no schema= kwarg):
  exam_papers              — faculty-configured exam papers
  exam_questions           — AI-generated questions per paper
  blooms_compliance_reports — Bloom's level distribution analysis per paper
  question_bank            — approved questions promoted for reuse (H-35 Addition 1)
  internal_marks_summary   — per-student internal assessment marks (H-35 Addition 2)

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
from sqlalchemy.orm import relationship, validates

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
    FAILED         = "FAILED"          # generation failed; faculty must retry
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


class ExamWorkflow(str, enum.Enum):
    """
    Drives which approval gates are enforced.
      INTERNAL   — Faculty-only gate (Quiz, Internal Test, Mid-Term).
                   No Board review; faculty self-approves then releases.
      BOARD_EXAM — Full 3-gate Board workflow (Semester, End-Semester, Supplementary).
    """
    INTERNAL   = "INTERNAL"
    BOARD_EXAM = "BOARD_EXAM"


class InternalMarkStatus(str, enum.Enum):
    PENDING           = "PENDING"
    FACULTY_SUBMITTED = "FACULTY_SUBMITTED"   # Gate 1: faculty submits
    DEAN_LOCKED       = "DEAN_LOCKED"         # Gate 2: Dean locks (immutable after)


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
        Index("ix_exam_papers_workflow",  "exam_workflow"),
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

    # Set when status == FAILED; human-readable reason from worker or queue
    failure_reason      = Column(Text, nullable=True)

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

    # --- H-35 productization additions ---

    # Workflow routing: INTERNAL (faculty-only gate) vs BOARD_EXAM (full 3-gate Board flow)
    exam_workflow       = Column(
        Enum(ExamWorkflow, native_enum=False),
        nullable=False,
        default=ExamWorkflow.BOARD_EXAM,
        server_default=ExamWorkflow.BOARD_EXAM.value,
    )

    # Optional Part A / Part B / Part C section structure
    # [{label, instruction, total_q, answer_q, marks_each, order}]
    section_config      = Column(JSONB, nullable=True)

    # Per-CO advisory coverage — written by generation worker
    # [{co_id, co_code, covered: bool, question_count: int}]
    co_coverage_report  = Column(JSONB, nullable=True)

    # Per-unit advisory coverage — written by generation worker
    # [{unit_no: int, covered: bool, question_count: int}]
    unit_coverage_report = Column(JSONB, nullable=True)

    # Optional scrutinizer (second faculty reviewer) — BOARD_EXAM workflow only
    scrutinizer_id      = Column(UUID(as_uuid=True), nullable=True)
    scrutinized_at      = Column(DateTime(timezone=True), nullable=True)
    scrutinizer_comment = Column(Text, nullable=True)

    # --- M08→M09 integration (H-36 STEP-01) ---

    # When True, each scanned_script for this paper requires two independent evaluators.
    # The M09 service checks this flag when assigning evaluators and enforcing
    # secondary evaluator Gate 1 before Board finalisation (STEP-08).
    double_evaluation_enabled = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    # Delta between primary and secondary evaluator totals (as % of max_marks)
    # that triggers a Board escalation flag in the M09 discrepancy detection step.
    # NULL = use the tenant default (20.0%). Only meaningful when double_evaluation_enabled=True.
    discrepancy_threshold_pct = Column(
        Numeric(4, 1),
        nullable=True,
        server_default="20.0",
    )

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
        Index("ix_exam_questions_paper",   "exam_paper_id"),
        Index("ix_exam_questions_bloom",   "bloom_level"),
        Index("ix_exam_questions_type",    "question_type"),
        Index("ix_exam_questions_unit",    "unit_number"),
        Index("ix_exam_questions_section", "section_label"),
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

    # --- H-35 productization additions ---

    # Section within the paper: "A", "B", "C"
    section_label   = Column(String(4), nullable=True)

    # Groups either/or pairs within a section (integer key, same value = paired)
    choice_group    = Column(Integer, nullable=True)

    # CO UUIDs from M02 CourseOutcome linked to this question (advisory)
    co_ids          = Column(JSONB, nullable=True, server_default="[]")

    created_at      = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at      = Column(DateTime(timezone=True), nullable=True)

    paper = relationship("ExamPaper", back_populates="questions")

    @validates("bloom_level")
    def _norm_bloom(self, _key: str, value: str) -> str:
        return value.upper().strip() if value else value

    @validates("question_type")
    def _norm_qtype(self, _key: str, value: str) -> str:
        return value.upper().replace(" ", "_").strip() if value else value


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

    # --- H-35 productization additions ---

    # Advisory flags — true when all COs / all requested units are represented
    co_coverage_ok   = Column(Boolean, nullable=True, server_default="false")
    unit_coverage_ok = Column(Boolean, nullable=True, server_default="false")

    generated_at    = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    paper = relationship("ExamPaper", back_populates="blooms_report")


# ---------------------------------------------------------------------------
# QuestionBankEntry  (H-35 Addition 1)
# ---------------------------------------------------------------------------

class QuestionBankEntry(Base):
    """
    A single approved question stored in the reusable question bank.

    Promotion invariants:
      - is_approved=True set ONLY when the source paper reaches BOARD_APPROVED (Gate 2).
      - Never promoted from FAILED, DRAFT, or GENERATING papers.
      - usage_count incremented each time the question is reused in a new paper.
      - source_paper_id SET NULL on paper deletion; bank entry is preserved.

    co_ids JSONB schema:  [uuid-string, ...]   — CO UUIDs from M02 CourseOutcome
    options JSONB schema: [{label, text}, ...]  — MCQ only
    marking_scheme JSONB: [{criterion, marks, description}, ...]
    """
    __tablename__ = "question_bank"
    __table_args__ = (
        Index("ix_qbank_course",   "course_id"),
        Index("ix_qbank_bloom",    "bloom_level"),
        Index("ix_qbank_type",     "question_type"),
        Index("ix_qbank_source",   "source_paper_id"),
        Index("ix_qbank_approved", "is_approved"),
        Index("ix_qbank_unit",     "unit_number"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Denormalised course reference (no schema-crossing FK)
    course_id       = Column(UUID(as_uuid=True), nullable=False)

    # Source paper — nullable; SET NULL on delete so bank survives paper deletion
    source_paper_id = Column(
        UUID(as_uuid=True),
        ForeignKey("exam_papers.id", ondelete="SET NULL"),
        nullable=True,
    )

    unit_number     = Column(Integer, nullable=False)
    co_ids          = Column(JSONB, nullable=True, server_default="[]")

    bloom_level     = Column(
        Enum(BloomLevel, native_enum=False),
        nullable=False,
    )
    question_type   = Column(
        Enum(QuestionType, native_enum=False),
        nullable=False,
    )

    question_text   = Column(Text, nullable=False)
    options         = Column(JSONB, nullable=True)
    correct_option  = Column(String, nullable=True)
    marks           = Column(Numeric(5, 1), nullable=False)
    model_answer    = Column(Text, nullable=True)
    marking_scheme  = Column(JSONB, nullable=True)
    section_label   = Column(String(4), nullable=True)

    # Human gate: True only after Board approves the source paper
    is_approved     = Column(Boolean, nullable=False, server_default="false", default=False)

    # Incremented each time this question is reused in a new paper
    usage_count     = Column(Integer, nullable=False, server_default="0", default=0)

    ai_generated    = Column(Boolean, nullable=False, server_default="true", default=True)

    created_at      = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at      = Column(DateTime(timezone=True), nullable=True)

    source_paper = relationship("ExamPaper", foreign_keys=[source_paper_id])


# ---------------------------------------------------------------------------
# InternalMarksSummary  (H-35 Addition 2)
# ---------------------------------------------------------------------------

class InternalMarksSummary(Base):
    """
    Per-student, per-course, per-semester internal assessment marks.

    Workflow:
      PENDING → FACULTY_SUBMITTED (Gate 1: faculty submits)
              → DEAN_LOCKED       (Gate 2: Dean locks; marks become immutable)

    Human-gate invariants:
      submitted_by + submitted_at set ONLY by faculty submit endpoint.
      locked_by + locked_at set ONLY by Dean lock endpoint.
      No system or Celery task ever advances status beyond PENDING.
      After DEAN_LOCKED: no further updates permitted (enforced at service layer).

    total_internal is computed by the service layer when faculty submits,
    as sum of component marks. Never set autonomously before faculty action.

    Unique constraint: one row per (student_id, course_id, academic_year, semester).
    """
    __tablename__ = "internal_marks_summary"
    __table_args__ = (
        Index("ix_ims_student",  "student_id"),
        Index("ix_ims_course",   "course_id"),
        Index("ix_ims_status",   "status"),
        Index("ix_ims_year_sem", "academic_year", "semester"),
        UniqueConstraint(
            "student_id", "course_id", "academic_year", "semester",
            name="uq_ims_student_course_year_sem",
        ),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Denormalised — no schema-crossing FK constraints
    student_id       = Column(UUID(as_uuid=True), nullable=False)
    course_id        = Column(UUID(as_uuid=True), nullable=False)
    semester         = Column(Integer, nullable=False)
    academic_year    = Column(String(10), nullable=False)   # e.g. "2025-26"

    # Component marks — filled incrementally, all nullable until submitted
    internal1_marks  = Column(Numeric(5, 1), nullable=True)
    internal2_marks  = Column(Numeric(5, 1), nullable=True)
    assignment_marks = Column(Numeric(5, 1), nullable=True)
    attendance_marks = Column(Numeric(5, 1), nullable=True)

    # Service layer computes this on submission (sum of components)
    total_internal   = Column(Numeric(5, 1), nullable=True)

    # Institution-configurable maximum (default 40)
    max_internal     = Column(Integer, nullable=False, server_default="40", default=40)

    status           = Column(
        Enum(InternalMarkStatus, native_enum=False),
        nullable=False,
        default=InternalMarkStatus.PENDING,
        server_default=InternalMarkStatus.PENDING.value,
    )

    # Gate 1: faculty submits
    submitted_by     = Column(UUID(as_uuid=True), nullable=True)
    submitted_at     = Column(DateTime(timezone=True), nullable=True)

    # Gate 2: Dean locks
    locked_by        = Column(UUID(as_uuid=True), nullable=True)
    locked_at        = Column(DateTime(timezone=True), nullable=True)

    created_at       = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at       = Column(DateTime(timezone=True), nullable=True)
