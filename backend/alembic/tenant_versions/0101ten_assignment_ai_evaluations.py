"""tenant: coursework AI evaluation results (M04 AI pipeline)

Revision ID: 0101ten
Revises: 0100ten
Create Date: 2026-07-20

Adds one new table, assignment_evaluations, holding the ADVISORY AI analysis of a
student submission (extracted text, suggested marks, feedback, rubric, Bloom/CO
analysis, internal similarity, and reliability metadata). Purely additive:

  * No existing table is touched. The evaluator's authoritative marks continue to
    live on assignment_submissions; nothing here is ever copied into them.
  * One row per submission (unique submission_id), written only by the background
    worker. A submission with no row simply has no AI analysis yet — every
    existing submission is unaffected and remains fully gradeable by hand.

Enum columns use native_enum=False (stored as VARCHAR), so future statuses need no
migration. Fully reversible.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0101ten"
down_revision = "0100ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "assignment_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "submission_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assignment_submissions.id", ondelete="CASCADE"),
            nullable=False, unique=True,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("file_type", sa.String(), nullable=True),
        sa.Column("suggested_marks", postgresql.JSONB(), nullable=True),
        sa.Column("overall_suggested_marks", sa.Numeric(6, 2), nullable=True),
        sa.Column("percentage", sa.Numeric(5, 2), nullable=True),
        sa.Column("confidence_level", sa.String(), nullable=True),
        sa.Column("feedback", postgresql.JSONB(), nullable=True),
        sa.Column("rubric_scores", postgresql.JSONB(), nullable=True),
        sa.Column("bloom_analysis", postgresql.JSONB(), nullable=True),
        sa.Column("co_analysis", postgresql.JSONB(), nullable=True),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("similarity_matches", postgresql.JSONB(), nullable=True),
        sa.Column("plagiarism_status", sa.String(), nullable=False, server_default="PLACEHOLDER"),
        sa.Column("ai_model", sa.String(), nullable=True),
        sa.Column("prompt_hash", sa.String(), nullable=True),
        sa.Column("processing_ms", sa.Integer(), nullable=True),
        sa.Column("error_log", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_assignment_evaluations_submission", "assignment_evaluations", ["submission_id"],
    )
    op.create_index(
        "ix_assignment_evaluations_status", "assignment_evaluations", ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_assignment_evaluations_status", table_name="assignment_evaluations")
    op.drop_index("ix_assignment_evaluations_submission", table_name="assignment_evaluations")
    op.drop_table("assignment_evaluations")
