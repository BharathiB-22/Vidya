"""
M10 Bell Curve Normaliser — SQLAlchemy models.

Tables (all tenant-schema, no schema= kwarg):
  bell_curve_analyses        — one record per exam paper per analysis run
  bell_curve_decisions       — Board ratification record (one per analysis)
  bell_curve_normalized_scores — append-only normalised marks (written only on Board ratification)

Human-gate invariants:
  bell_curve_analyses.status → APPLIED / NO_ACTION only via board ratify endpoint (Gate 1).
  No Celery task ever sets status beyond READY.
  bell_curve_decisions is NEVER written by any Celery task.
  bell_curve_normalized_scores is NEVER written by any Celery task.
  bell_curve_normalized_scores has NO UPDATE or DELETE — append-only.
  exam_score_ledger (M09) is NEVER modified by any M10 code.

Enum columns stored as sa.String() in DB (no PostgreSQL ENUM type).
Python Enum classes provide type safety in application code.
Tenant isolation: all tables live in the tenant schema.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Column, DateTime, Enum, ForeignKey,
    Index, Integer, Numeric, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AnalysisStatus(str, enum.Enum):
    PENDING        = "PENDING"         # analysis record created; Celery job not yet started
    ANALYSING      = "ANALYSING"       # Celery job running
    READY          = "READY"           # analysis complete; awaiting Board review
    BOARD_REVIEWED = "BOARD_REVIEWED"  # Board opened the panel (informational; no action yet)
    APPLIED        = "APPLIED"         # Gate 1: Board ratified; normalisation written to ledger
    NO_ACTION      = "NO_ACTION"       # Gate 1: Board explicitly rejected normalisation
    FAILED         = "FAILED"          # Celery job failed


class BoardDecision(str, enum.Enum):
    ACCEPTED_SUGGESTION = "ACCEPTED_SUGGESTION"  # Board accepted AI suggestion as-is
    MODIFIED            = "MODIFIED"             # Board modified the suggestion parameters
    REJECTED            = "REJECTED"             # Board rejected normalisation (raw scores stand)


class NormalisationMethod(str, enum.Enum):
    LINEAR_SCALE   = "LINEAR_SCALE"    # score_new = min(score * k, max_marks)
    PERCENTILE_MAP = "PERCENTILE_MAP"  # normalised = percentile_rank/100 * target_max
    BOUNDARY_SHIFT = "BOUNDARY_SHIFT"  # shift grade cut-off boundaries; raw score unchanged
    NONE           = "NONE"            # no normalisation; M09 raw scores are final
    CUSTOM         = "CUSTOM"          # Board-supplied per-student score deltas


# ---------------------------------------------------------------------------
# BellCurveAnalysis
# ---------------------------------------------------------------------------

class BellCurveAnalysis(Base):
    """
    One record per exam paper per analysis run.

    Written by the Celery task (status up to READY only).
    Status → APPLIED or NO_ACTION only via Board ratification endpoint (Gate 1).
    exam_score_ledger (M09) is READ ONLY by this module — never modified.

    raw_stats JSONB:
      {mean, std, median, min, max, skewness, kurtosis, q1, q3,
       histogram: [{bin_start, bin_end, count}]}

    anomalies JSONB:
      [{type, severity, description, threshold, observed_value}]

    normalisation_suggestion JSONB:
      {method, params, reasoning, projected_stats}

    cross_evaluator_stats JSONB:
      [{evaluator_id, mean, std, count, z_score, is_outlier}]
    """
    __tablename__ = "bell_curve_analyses"
    __table_args__ = (
        Index("ix_bc_analyses_exam_paper",   "exam_paper_id"),
        Index("ix_bc_analyses_status",       "status"),
        Index("ix_bc_analyses_triggered_by", "triggered_by"),
        Index("ix_bc_analyses_created",      "created_at"),
    )

    id                     = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # FK to M08 exam_papers.id (cross-module; no ORM-level FK — same tenant schema)
    exam_paper_id          = Column(UUID(as_uuid=True), nullable=False)

    # Celery task_jobs.id reference (public schema)
    analysis_job_id        = Column(UUID(as_uuid=True), nullable=True)

    # Number of finalised scripts analysed (from exam_score_ledger)
    score_count            = Column(Integer, nullable=True)

    # Statistical summary — written by Celery task
    raw_stats              = Column(JSONB, nullable=True)
    anomalies              = Column(JSONB, nullable=True)
    normalisation_suggestion = Column(JSONB, nullable=True)
    cross_evaluator_stats  = Column(JSONB, nullable=True)

    # Who triggered the analysis
    triggered_by           = Column(UUID(as_uuid=True), nullable=False)

    # Workflow — Celery never sets beyond READY
    status                 = Column(
        Enum(AnalysisStatus, native_enum=False),
        nullable=False,
        default=AnalysisStatus.PENDING,
    )

    triggered_at           = Column(DateTime(timezone=True), nullable=True)
    analysis_completed_at  = Column(DateTime(timezone=True), nullable=True)
    created_at             = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    decision = relationship(
        "BellCurveDecision",
        back_populates="analysis",
        uselist=False,
    )


# ---------------------------------------------------------------------------
# BellCurveDecision
# ---------------------------------------------------------------------------

class BellCurveDecision(Base):
    """
    Board ratification record — written ONLY by the ratify endpoint (Gate 1).
    One decision per analysis (UniqueConstraint on analysis_id).
    Never updated or deleted after creation.

    normalisation_params JSONB:
      LINEAR_SCALE:   {scale_factor: float}
      PERCENTILE_MAP: {target_mean: float, target_max: float}
      BOUNDARY_SHIFT: {shift_amount: float, direction: "UP"|"DOWN"}
      NONE:           {}
      CUSTOM:         {adjustments: [{student_roll_ref, delta}]}

    projected_stats JSONB:
      {mean, std, median, min, max, skewness} — computed at ratification time
    """
    __tablename__ = "bell_curve_decisions"
    __table_args__ = (
        UniqueConstraint("analysis_id", name="uq_bc_decision_analysis"),
        Index("ix_bc_decisions_analysis",    "analysis_id"),
        Index("ix_bc_decisions_exam_paper",  "exam_paper_id"),
        Index("ix_bc_decisions_ratified_by", "ratified_by"),
        Index("ix_bc_decisions_ratified_at", "ratified_at"),
    )

    id                    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id           = Column(
        UUID(as_uuid=True),
        ForeignKey("bell_curve_analyses.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )

    # Denormalized for reporting without joining to analyses
    exam_paper_id         = Column(UUID(as_uuid=True), nullable=False)

    # Board decision type
    decision              = Column(
        Enum(BoardDecision, native_enum=False),
        nullable=False,
    )

    # Normalisation method applied
    normalisation_method  = Column(
        Enum(NormalisationMethod, native_enum=False),
        nullable=False,
    )

    # Actual params used (varies by method)
    normalisation_params  = Column(JSONB, nullable=False, default=dict)

    # Projected outcome stats — computed at ratification time
    projected_stats       = Column(JSONB, nullable=True)

    # Board member who ratified — mandatory; never null
    ratified_by           = Column(UUID(as_uuid=True), nullable=False)
    ratification_note     = Column(Text, nullable=True)
    ratified_at           = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    analysis = relationship("BellCurveAnalysis", back_populates="decision")
    normalized_scores = relationship(
        "BellCurveNormalisedScore",
        back_populates="decision",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# BellCurveNormalisedScore — append-only; no UPDATE or DELETE ever
# ---------------------------------------------------------------------------

class BellCurveNormalisedScore(Base):
    """
    Immutable record of a Board-ratified normalised score for one student.

    Written ONCE by the ratify service method (Gate 1).
    Never updated or deleted — this is the normalised grade record.

    raw_score:        copied from exam_score_ledger.total_marks at ratification time
    normalised_score: result of applying the normalisation method
    max_marks:        copied from exam_score_ledger.max_marks

    student_user_id / student_roll_ref: copied from exam_score_ledger after
      identity has been revealed (all scripts BOARD_FINALISED before analysis
      is allowed).
    """
    __tablename__ = "bell_curve_normalized_scores"
    __table_args__ = (
        Index("ix_bc_norm_scores_decision",    "decision_id"),
        Index("ix_bc_norm_scores_analysis",    "analysis_id"),
        Index("ix_bc_norm_scores_exam_paper",  "exam_paper_id"),
        Index("ix_bc_norm_scores_student",     "student_user_id"),
        Index("ix_bc_norm_scores_created",     "created_at"),
    )

    id                    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_id           = Column(
        UUID(as_uuid=True),
        ForeignKey("bell_curve_decisions.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Denormalized for reporting
    analysis_id           = Column(UUID(as_uuid=True), nullable=False)
    exam_paper_id         = Column(UUID(as_uuid=True), nullable=False)

    # Student identity — copied from exam_score_ledger at ratification time
    student_user_id       = Column(UUID(as_uuid=True), nullable=True)
    student_roll_ref      = Column(String, nullable=True)

    # Scores
    raw_score             = Column(Numeric(6, 2), nullable=False)
    normalised_score      = Column(Numeric(6, 2), nullable=False)
    max_marks             = Column(Numeric(6, 2), nullable=False)

    # Denormalized for reporting without joining to decisions
    normalisation_method  = Column(String, nullable=False)

    created_at            = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    decision = relationship("BellCurveDecision", back_populates="normalized_scores")
