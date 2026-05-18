"""tenant: create m08 exam setter tables

Revision ID: 0011ten
Revises: 0010ten
Create Date: 2026-05-18

Tables created (tenant schema):
  exam_papers              — faculty-configured exam papers
  exam_questions           — AI-generated questions per paper
  blooms_compliance_reports — Bloom's level distribution analysis

Human-gate invariants:
  exam_papers.status → SUBMITTED only via faculty submit endpoint (Gate 1).
  exam_papers.status → BOARD_APPROVED / BOARD_RETURNED only via board decision endpoint (Gate 2).
  exam_papers.status → SEALED only via faculty seal endpoint (Gate 3).
  exam_papers.status → RELEASED only via Celery release task.
  No Celery task ever sets status beyond GENERATED.
  Model answers are never accessible when status == SEALED.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0011ten"
down_revision = "0010ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. exam_papers
    # ------------------------------------------------------------------
    op.create_table(
        "exam_papers",
        sa.Column("id",                   postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("course_id",            postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by",           postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title",                sa.String(),                   nullable=False),
        sa.Column("exam_type",            sa.String(),                   nullable=False, server_default="END_SEM"),
        sa.Column("total_marks",          sa.Integer(),                  nullable=False, server_default="100"),
        sa.Column("duration_mins",        sa.Integer(),                  nullable=False, server_default="180"),
        # Which syllabus units to cover: [1, 2, 3]
        sa.Column("units_included",       postgresql.JSONB(),            nullable=False, server_default="[]"),
        # Question format counts: {mcq_count, short_count, long_count, problem_count}
        sa.Column("question_format",      postgresql.JSONB(),            nullable=False, server_default="{}"),
        # Bloom's % distributions: {remember, understand, apply, analyse, evaluate, create}
        sa.Column("requested_dist",       postgresql.JSONB(),            nullable=False, server_default="{}"),
        sa.Column("actual_dist",          postgresql.JSONB(),            nullable=True),
        sa.Column("special_instructions", sa.Text(),                     nullable=True),
        # AI provenance
        sa.Column("ai_model",             sa.String(),                   nullable=True),
        sa.Column("prompt_hash",          sa.String(),                   nullable=True),
        sa.Column("generation_job_id",    postgresql.UUID(as_uuid=True), nullable=True),
        # Workflow status — never modified by any Celery task beyond GENERATED
        sa.Column("status",               sa.String(),                   nullable=False, server_default="DRAFT"),
        # Gate 1: faculty submits for Board review
        sa.Column("submitted_at",         sa.DateTime(timezone=True),    nullable=True),
        # Gate 2: board decision — ONLY written by board decision endpoint
        sa.Column("approved_by",          postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at",          sa.DateTime(timezone=True),    nullable=True),
        sa.Column("board_comment",        sa.Text(),                     nullable=True),
        # Gate 3: seal — ONLY written by seal endpoint
        sa.Column("sealed_at",            sa.DateTime(timezone=True),    nullable=True),
        sa.Column("release_at",           sa.DateTime(timezone=True),    nullable=True),
        # Encryption references (NOT the key itself)
        sa.Column("encrypted_blob_key",   sa.String(),                   nullable=True),
        sa.Column("encryption_key_ref",   sa.String(),                   nullable=True),
        # Release job FK
        sa.Column("release_job_id",       postgresql.UUID(as_uuid=True), nullable=True),
        # Written by release Celery task only
        sa.Column("released_at",          sa.DateTime(timezone=True),    nullable=True),
        sa.Column("created_at",           sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",           sa.DateTime(timezone=True),    nullable=True),
    )
    op.create_index("ix_exam_papers_course",   "exam_papers", ["course_id"])
    op.create_index("ix_exam_papers_creator",  "exam_papers", ["created_by"])
    op.create_index("ix_exam_papers_status",   "exam_papers", ["status"])
    op.create_index("ix_exam_papers_created",  "exam_papers", ["created_at"])
    op.create_index("ix_exam_papers_release",  "exam_papers", ["release_at"])

    # ------------------------------------------------------------------
    # 2. exam_questions
    # ------------------------------------------------------------------
    op.create_table(
        "exam_questions",
        sa.Column("id",              postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exam_paper_id",   postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("exam_papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unit_number",     sa.Integer(),                   nullable=False),
        sa.Column("co_code",         sa.String(),                    nullable=True),
        sa.Column("bloom_level",     sa.String(),                    nullable=False),
        sa.Column("question_type",   sa.String(),                    nullable=False),
        sa.Column("question_text",   sa.Text(),                      nullable=False),
        # [{label:"A", text:"..."}] — MCQ only
        sa.Column("options",         postgresql.JSONB(),              nullable=True),
        # Correct MCQ option label — ONLY in model answers export (role-gated)
        sa.Column("correct_option",  sa.String(),                    nullable=True),
        sa.Column("marks",           sa.Numeric(5, 1),               nullable=False),
        # Model answer — NOT exposed when paper status == SEALED
        sa.Column("model_answer",    sa.Text(),                      nullable=True),
        # [{criterion, marks, description}]
        sa.Column("marking_scheme",  postgresql.JSONB(),              nullable=True),
        # ["A","B"] or ["A"] — set membership
        sa.Column("set_membership",  postgresql.JSONB(),              nullable=False, server_default='["A","B"]'),
        sa.Column("ai_generated",    sa.Boolean(),                   nullable=False, server_default="true"),
        sa.Column("is_edited",       sa.Boolean(),                   nullable=False, server_default="false"),
        sa.Column("created_at",      sa.DateTime(timezone=True),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",      sa.DateTime(timezone=True),     nullable=True),
    )
    op.create_index("ix_exam_questions_paper", "exam_questions", ["exam_paper_id"])
    op.create_index("ix_exam_questions_bloom", "exam_questions", ["bloom_level"])
    op.create_index("ix_exam_questions_type",  "exam_questions", ["question_type"])
    op.create_index("ix_exam_questions_unit",  "exam_questions", ["unit_number"])

    # ------------------------------------------------------------------
    # 3. blooms_compliance_reports
    # ------------------------------------------------------------------
    op.create_table(
        "blooms_compliance_reports",
        sa.Column("id",             postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exam_paper_id",  postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("exam_papers.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("requested_dist", postgresql.JSONB(),            nullable=False),
        sa.Column("actual_dist",    postgresql.JSONB(),            nullable=False),
        sa.Column("compliance_ok",  sa.Boolean(),                  nullable=False, server_default="false"),
        # [{level, requested_pct, actual_pct, delta_pct}]
        sa.Column("violations",     postgresql.JSONB(),            nullable=False, server_default="[]"),
        sa.Column("generated_at",   sa.DateTime(timezone=True),   nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_blooms_report_paper", "blooms_compliance_reports", ["exam_paper_id"]
    )
    op.create_index("ix_blooms_report_paper", "blooms_compliance_reports", ["exam_paper_id"])


def downgrade() -> None:
    op.drop_table("blooms_compliance_reports")
    op.drop_table("exam_questions")
    op.drop_table("exam_papers")
