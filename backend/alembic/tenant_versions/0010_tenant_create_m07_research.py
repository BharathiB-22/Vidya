"""tenant: create m07 research supervision tables

Revision ID: 0010ten
Revises: 0009ten
Create Date: 2026-05-18

Tables created (tenant schema):
  research_problems   — student-proposed or AI-generated research problems
  research_documents  — versioned document uploads per research problem
  viva_sessions       — async video viva sessions per document

Human-gate invariants:
  research_problems.status  → never set to ACCEPTED/REJECTED by any task
  research_documents.status → never set to APPROVED by any task
  viva_sessions.status      → never set to GUIDE_RATIFIED by any task
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0010ten"
down_revision = "0009ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. research_problems
    # ------------------------------------------------------------------
    op.create_table(
        "research_problems",
        sa.Column("id",                 postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("guide_user_id",      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_user_id",    postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title",              sa.String(),                   nullable=False),
        sa.Column("abstract",           sa.Text(),                     nullable=True),
        # [{question: str}]
        sa.Column("research_questions", postgresql.JSONB(),            nullable=False, server_default="[]"),
        sa.Column("source",             sa.String(),                   nullable=False, server_default="STUDENT_PROPOSED"),
        # AI evaluation scores (written by Celery task only)
        sa.Column("novelty_score",      sa.Numeric(4, 3),              nullable=True),
        sa.Column("feasibility_score",  sa.Numeric(4, 3),              nullable=True),
        sa.Column("clarity_score",      sa.Numeric(4, 3),              nullable=True),
        sa.Column("ai_recommendation",  sa.String(),                   nullable=True),
        sa.Column("ai_reasoning",       sa.Text(),                     nullable=True),
        sa.Column("ai_model",           sa.String(),                   nullable=True),
        sa.Column("prompt_hash",        sa.String(),                   nullable=True),
        sa.Column("eval_job_id",        postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status",             sa.String(),                   nullable=False, server_default="PENDING_REVIEW"),
        # Guide decision — ONLY written by guide decision endpoint
        sa.Column("guide_decision",     sa.String(),                   nullable=True),
        sa.Column("guide_note",         sa.Text(),                     nullable=True),
        sa.Column("decided_at",         sa.DateTime(timezone=True),    nullable=True),
        sa.Column("created_at",         sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",         sa.DateTime(timezone=True),    nullable=True),
    )
    op.create_index("ix_research_problems_guide",   "research_problems", ["guide_user_id"])
    op.create_index("ix_research_problems_student", "research_problems", ["student_user_id"])
    op.create_index("ix_research_problems_status",  "research_problems", ["status"])
    op.create_index("ix_research_problems_source",  "research_problems", ["source"])
    op.create_index("ix_research_problems_created", "research_problems", ["created_at"])

    # ------------------------------------------------------------------
    # 2. research_documents
    # ------------------------------------------------------------------
    op.create_table(
        "research_documents",
        sa.Column("id",                   postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("research_problem_id",  postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("research_problems.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_user_id",      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version",              sa.Integer(),                  nullable=False, server_default="1"),
        sa.Column("file_url",             sa.String(),                   nullable=True),
        sa.Column("file_name",            sa.String(),                   nullable=True),
        # AI evaluation scores (written by Celery task only)
        sa.Column("plagiarism_score",     sa.Float(),                    nullable=True),
        sa.Column("ai_content_score",     sa.Float(),                    nullable=True),
        sa.Column("format_score",         sa.Float(),                    nullable=True),
        sa.Column("clarity_score",        sa.Float(),                    nullable=True),
        # Full structured evaluation report
        sa.Column("evaluation_report",    postgresql.JSONB(),            nullable=True),
        sa.Column("ai_model",             sa.String(),                   nullable=True),
        sa.Column("prompt_hash",          sa.String(),                   nullable=True),
        sa.Column("eval_job_id",          postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status",               sa.String(),                   nullable=False, server_default="SUBMITTED"),
        # Guide review — ONLY written by guide review endpoint
        sa.Column("guide_comment",        sa.Text(),                     nullable=True),
        sa.Column("guide_reviewed_at",    sa.DateTime(timezone=True),    nullable=True),
        sa.Column("submitted_at",         sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_research_documents_problem",  "research_documents", ["research_problem_id"])
    op.create_index("ix_research_documents_student",  "research_documents", ["student_user_id"])
    op.create_index("ix_research_documents_status",   "research_documents", ["status"])
    op.create_index("ix_research_documents_version",  "research_documents", ["research_problem_id", "version"])

    # ------------------------------------------------------------------
    # 3. viva_sessions
    # ------------------------------------------------------------------
    op.create_table(
        "viva_sessions",
        sa.Column("id",                   postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("research_problem_id",  postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("research_problems.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id",          postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("research_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_user_id",      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("guide_user_id",        postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_token",        sa.String(),                   nullable=False, unique=True),
        # AI-generated questions
        sa.Column("ai_questions",         postgresql.JSONB(),            nullable=False, server_default="[]"),
        # Student responses accumulated during session
        sa.Column("ai_responses",         postgresql.JSONB(),            nullable=False, server_default="[]"),
        # Recording
        sa.Column("video_url",            sa.String(),                   nullable=True),
        sa.Column("transcript",           sa.Text(),                     nullable=True),
        # AI evaluation (written by Celery process_viva_session task only)
        sa.Column("ai_evaluation",        postgresql.JSONB(),            nullable=True),
        sa.Column("overall_ai_score",     sa.Numeric(5, 2),              nullable=True),
        # Guide evaluation (ONLY written by guide ratify endpoint — human gate)
        sa.Column("guide_evaluation",     postgresql.JSONB(),            nullable=True),
        sa.Column("overall_guide_score",  sa.Numeric(5, 2),              nullable=True),
        # DPDP consent
        sa.Column("consent_recorded",     sa.Boolean(),                  nullable=False, server_default="false"),
        # AI provenance
        sa.Column("ai_model",             sa.String(),                   nullable=True),
        sa.Column("eval_job_id",          postgresql.UUID(as_uuid=True), nullable=True),
        # Timestamps
        sa.Column("scheduled_at",         sa.DateTime(timezone=True),    nullable=True),
        sa.Column("expires_at",           sa.DateTime(timezone=True),    nullable=True),
        sa.Column("completed_at",         sa.DateTime(timezone=True),    nullable=True),
        sa.Column("ratified_at",          sa.DateTime(timezone=True),    nullable=True),
        sa.Column("status",               sa.String(),                   nullable=False, server_default="SCHEDULED"),
    )
    op.create_unique_constraint("uq_viva_sessions_token",    "viva_sessions", ["session_token"])
    op.create_index("ix_viva_sessions_problem",   "viva_sessions", ["research_problem_id"])
    op.create_index("ix_viva_sessions_document",  "viva_sessions", ["document_id"])
    op.create_index("ix_viva_sessions_student",   "viva_sessions", ["student_user_id"])
    op.create_index("ix_viva_sessions_guide",     "viva_sessions", ["guide_user_id"])
    op.create_index("ix_viva_sessions_token",     "viva_sessions", ["session_token"])
    op.create_index("ix_viva_sessions_status",    "viva_sessions", ["status"])
    op.create_index("ix_viva_sessions_scheduled", "viva_sessions", ["scheduled_at"])


def downgrade() -> None:
    op.drop_table("viva_sessions")
    op.drop_table("research_documents")
    op.drop_table("research_problems")
