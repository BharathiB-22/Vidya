"""tenant: create m10 bell curve normaliser tables

Revision ID: 0013ten
Revises: 0012ten
Create Date: 2026-05-19

Tables created (tenant schema):
  bell_curve_analyses        — one record per exam paper per analysis run
  bell_curve_decisions       — Board ratification record (one per analysis)
  bell_curve_normalized_scores — append-only Board-ratified normalised marks

Human-gate invariants:
  bell_curve_analyses.status → APPLIED / NO_ACTION only via Board ratify endpoint (Gate 1).
  No Celery task ever sets status beyond READY.
  bell_curve_decisions is NEVER written by any Celery task.
  bell_curve_normalized_scores is NEVER written by any Celery task.
  bell_curve_normalized_scores has NO UPDATE or DELETE — append-only.
  exam_score_ledger (M09) is NEVER modified by M10.

Enum columns stored as sa.String() — no PostgreSQL ENUM type.
Consistent with all prior tenant_versions migrations (0001ten–0012ten).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0013ten"
down_revision = "0012ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. bell_curve_analyses
    # ------------------------------------------------------------------
    op.create_table(
        "bell_curve_analyses",
        sa.Column("id",                      postgresql.UUID(as_uuid=True), primary_key=True),
        # FK to M08 exam_papers.id (same tenant schema; no ORM-level FK)
        sa.Column("exam_paper_id",           postgresql.UUID(as_uuid=True), nullable=False),
        # Celery task_jobs.id (public schema)
        sa.Column("analysis_job_id",         postgresql.UUID(as_uuid=True), nullable=True),
        # Number of finalised scripts analysed
        sa.Column("score_count",             sa.Integer(),                  nullable=True),
        # Statistical payload — written by Celery task
        sa.Column("raw_stats",               postgresql.JSONB(),            nullable=True),
        sa.Column("anomalies",               postgresql.JSONB(),            nullable=True),
        sa.Column("normalisation_suggestion",postgresql.JSONB(),            nullable=True),
        sa.Column("cross_evaluator_stats",   postgresql.JSONB(),            nullable=True),
        # Who triggered
        sa.Column("triggered_by",            postgresql.UUID(as_uuid=True), nullable=False),
        # Workflow — Celery never sets beyond READY
        sa.Column("status",                  sa.String(),                   nullable=False, server_default="PENDING"),
        sa.Column("triggered_at",            sa.DateTime(timezone=True),    nullable=True),
        sa.Column("analysis_completed_at",   sa.DateTime(timezone=True),    nullable=True),
        sa.Column("created_at",              sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_bc_analyses_exam_paper",   "bell_curve_analyses", ["exam_paper_id"])
    op.create_index("ix_bc_analyses_status",       "bell_curve_analyses", ["status"])
    op.create_index("ix_bc_analyses_triggered_by", "bell_curve_analyses", ["triggered_by"])
    op.create_index("ix_bc_analyses_created",      "bell_curve_analyses", ["created_at"])

    # ------------------------------------------------------------------
    # 2. bell_curve_decisions  — written ONLY by Board ratify endpoint (Gate 1)
    # ------------------------------------------------------------------
    op.create_table(
        "bell_curve_decisions",
        sa.Column("id",                   postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_id",          postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bell_curve_analyses.id", ondelete="RESTRICT"),
                  nullable=False, unique=True),
        # Denormalized for reporting
        sa.Column("exam_paper_id",        postgresql.UUID(as_uuid=True), nullable=False),
        # Board decision
        sa.Column("decision",             sa.String(),                   nullable=False),
        sa.Column("normalisation_method", sa.String(),                   nullable=False),
        # Params and projected stats (vary by method)
        sa.Column("normalisation_params", postgresql.JSONB(),            nullable=False, server_default="{}"),
        sa.Column("projected_stats",      postgresql.JSONB(),            nullable=True),
        # Board member who ratified — mandatory
        sa.Column("ratified_by",          postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ratification_note",    sa.Text(),                     nullable=True),
        sa.Column("ratified_at",          sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_bc_decision_analysis", "bell_curve_decisions", ["analysis_id"]
    )
    op.create_index("ix_bc_decisions_analysis",    "bell_curve_decisions", ["analysis_id"])
    op.create_index("ix_bc_decisions_exam_paper",  "bell_curve_decisions", ["exam_paper_id"])
    op.create_index("ix_bc_decisions_ratified_by", "bell_curve_decisions", ["ratified_by"])
    op.create_index("ix_bc_decisions_ratified_at", "bell_curve_decisions", ["ratified_at"])

    # ------------------------------------------------------------------
    # 3. bell_curve_normalized_scores  — append-only; no UPDATE or DELETE ever
    # ------------------------------------------------------------------
    op.create_table(
        "bell_curve_normalized_scores",
        sa.Column("id",                   postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("decision_id",          postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bell_curve_decisions.id", ondelete="RESTRICT"),
                  nullable=False),
        # Denormalized
        sa.Column("analysis_id",          postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exam_paper_id",        postgresql.UUID(as_uuid=True), nullable=False),
        # Student identity — copied from exam_score_ledger at ratification time
        sa.Column("student_user_id",      postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("student_roll_ref",     sa.String(),                   nullable=True),
        # Scores
        sa.Column("raw_score",            sa.Numeric(6, 2),              nullable=False),
        sa.Column("normalised_score",     sa.Numeric(6, 2),              nullable=False),
        sa.Column("max_marks",            sa.Numeric(6, 2),              nullable=False),
        # Denormalized method for reporting
        sa.Column("normalisation_method", sa.String(),                   nullable=False),
        sa.Column("created_at",           sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_bc_norm_scores_decision",   "bell_curve_normalized_scores", ["decision_id"])
    op.create_index("ix_bc_norm_scores_analysis",   "bell_curve_normalized_scores", ["analysis_id"])
    op.create_index("ix_bc_norm_scores_exam_paper", "bell_curve_normalized_scores", ["exam_paper_id"])
    op.create_index("ix_bc_norm_scores_student",    "bell_curve_normalized_scores", ["student_user_id"])
    op.create_index("ix_bc_norm_scores_created",    "bell_curve_normalized_scores", ["created_at"])


def downgrade() -> None:
    op.drop_table("bell_curve_normalized_scores")
    op.drop_table("bell_curve_decisions")
    op.drop_table("bell_curve_analyses")
