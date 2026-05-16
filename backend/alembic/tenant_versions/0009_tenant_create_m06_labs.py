"""tenant: create m06 labs & assignment evaluator tables

Revision ID: 0009ten
Revises: 0008ten
Create Date: 2026-05-16

Tables created (tenant schema):
  lab_assignments  — faculty-published assignments (WRITTEN or CODE)
  lab_submissions  — one per student per assignment
  lab_evaluations  — AI evaluation result (1:1 with lab_submissions)
  grade_ledger     — append-only ratified marks; human-gate invariant
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0009ten"
down_revision = "0008ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # 1. lab_assignments
    op.create_table(
        "lab_assignments",
        sa.Column("id",                   postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("syllabus_id",          postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kit_assignment_id",    postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id",   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title",                sa.String(),                   nullable=False),
        sa.Column("description",          sa.Text(),                     nullable=True),
        sa.Column("submission_type",      sa.String(),                   nullable=False, server_default="WRITTEN"),
        sa.Column("language",             sa.String(),                   nullable=True),
        # [{criterion_id, name, description, max_marks, weight}]
        sa.Column("rubric",               postgresql.JSONB(),             nullable=False, server_default="[]"),
        # [{id, name, stdin, expected_stdout, is_hidden, points}] — CODE only
        sa.Column("test_cases",           postgresql.JSONB(),             nullable=False, server_default="[]"),
        sa.Column("max_marks",            sa.Integer(),                  nullable=True),
        sa.Column("deadline",             sa.DateTime(timezone=True),    nullable=True),
        sa.Column("ai_not_permitted",     sa.Boolean(),                  nullable=False, server_default="true"),
        sa.Column("allow_late",           sa.Boolean(),                  nullable=False, server_default="false"),
        sa.Column("plagiarism_threshold", sa.Numeric(4, 3),              nullable=False, server_default="0.850"),
        sa.Column("status",               sa.String(),                   nullable=False, server_default="DRAFT"),
        sa.Column("published_at",         sa.DateTime(timezone=True),    nullable=True),
        sa.Column("closed_at",            sa.DateTime(timezone=True),    nullable=True),
        sa.Column("created_at",           sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",           sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["syllabus_id"], ["syllabi.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_lab_assignments_syllabus",        "lab_assignments", ["syllabus_id"])
    op.create_index("ix_lab_assignments_created_by",      "lab_assignments", ["created_by_user_id"])
    op.create_index("ix_lab_assignments_status",          "lab_assignments", ["status"])
    op.create_index("ix_lab_assignments_submission_type", "lab_assignments", ["submission_type"])

    # 2. lab_submissions
    op.create_table(
        "lab_submissions",
        sa.Column("id",                postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_user_id",   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_type",   sa.String(),                   nullable=False),
        sa.Column("content_url",       sa.String(),                   nullable=True),
        sa.Column("content_text",      sa.Text(),                     nullable=True),
        sa.Column("submitted_at",      sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("is_late",           sa.Boolean(),                  nullable=False, server_default="false"),
        sa.Column("eval_job_id",       postgresql.UUID(as_uuid=True), nullable=True),
        # {probability, confidence, highlights[]}
        sa.Column("ai_scan_result",    postgresql.JSONB(),             nullable=True),
        sa.Column("ai_scan_status",    sa.String(),                   nullable=False, server_default="PENDING"),
        sa.Column("status",            sa.String(),                   nullable=False, server_default="SUBMITTED"),
        sa.ForeignKeyConstraint(["assignment_id"], ["lab_assignments.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_lab_submissions_assignment",         "lab_submissions", ["assignment_id"])
    op.create_index("ix_lab_submissions_student",            "lab_submissions", ["student_user_id"])
    op.create_index("ix_lab_submissions_assignment_student", "lab_submissions", ["assignment_id", "student_user_id"])
    op.create_index("ix_lab_submissions_status",             "lab_submissions", ["status"])
    op.create_index("ix_lab_submissions_ai_scan_status",     "lab_submissions", ["ai_scan_status"])

    # 3. lab_evaluations (1:1 with lab_submissions)
    op.create_table(
        "lab_evaluations",
        sa.Column("id",                  postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id",       postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        # [{criterion_id, ai_score, ai_justification, human_score, human_note}]
        sa.Column("rubric_scores",       postgresql.JSONB(),             nullable=False, server_default="[]"),
        sa.Column("overall_ai_score",    sa.Numeric(6, 2),               nullable=True),
        sa.Column("overall_human_score", sa.Numeric(6, 2),               nullable=True),
        sa.Column("confidence_level",    sa.String(),                    nullable=True),
        # CODE only
        sa.Column("test_results",        postgresql.JSONB(),             nullable=True),
        sa.Column("static_analysis",     postgresql.JSONB(),             nullable=True),
        # Plagiarism
        sa.Column("plagiarism_score",    sa.Float(),                     nullable=True),
        sa.Column("plagiarism_matches",  postgresql.JSONB(),             nullable=True),
        # Provenance
        sa.Column("ai_model",            sa.String(),                    nullable=True),
        sa.Column("prompt_hash",         sa.String(),                    nullable=True),
        sa.Column("created_at",          sa.DateTime(timezone=True),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",          sa.DateTime(timezone=True),     nullable=True),
        sa.ForeignKeyConstraint(["submission_id"], ["lab_submissions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("submission_id", name="uq_lab_evaluations_submission"),
    )
    op.create_index("ix_lab_evaluations_submission", "lab_evaluations", ["submission_id"])
    op.create_index("ix_lab_evaluations_confidence", "lab_evaluations", ["confidence_level"])

    # 4. grade_ledger — append-only; no UPDATE or DELETE ever
    op.create_table(
        "grade_ledger",
        sa.Column("id",                  postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id",       postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("assignment_id",       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_user_id",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ratified_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("final_score",         sa.Numeric(6, 2),               nullable=False),
        sa.Column("max_marks",           sa.Integer(),                   nullable=False),
        sa.Column("ratification_note",   sa.Text(),                      nullable=True),
        sa.Column("ratified_at",         sa.DateTime(timezone=True),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["submission_id"], ["lab_submissions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("submission_id", name="uq_grade_ledger_submission"),
    )
    op.create_index("ix_grade_ledger_submission",  "grade_ledger", ["submission_id"])
    op.create_index("ix_grade_ledger_assignment",  "grade_ledger", ["assignment_id"])
    op.create_index("ix_grade_ledger_student",     "grade_ledger", ["student_user_id"])
    op.create_index("ix_grade_ledger_ratified_by", "grade_ledger", ["ratified_by_user_id"])
    op.create_index("ix_grade_ledger_ratified_at", "grade_ledger", ["ratified_at"])


def downgrade() -> None:
    op.drop_index("ix_grade_ledger_ratified_at",  table_name="grade_ledger")
    op.drop_index("ix_grade_ledger_ratified_by",  table_name="grade_ledger")
    op.drop_index("ix_grade_ledger_student",      table_name="grade_ledger")
    op.drop_index("ix_grade_ledger_assignment",   table_name="grade_ledger")
    op.drop_index("ix_grade_ledger_submission",   table_name="grade_ledger")
    op.drop_table("grade_ledger")

    op.drop_index("ix_lab_evaluations_confidence", table_name="lab_evaluations")
    op.drop_index("ix_lab_evaluations_submission",  table_name="lab_evaluations")
    op.drop_table("lab_evaluations")

    op.drop_index("ix_lab_submissions_ai_scan_status",     table_name="lab_submissions")
    op.drop_index("ix_lab_submissions_status",             table_name="lab_submissions")
    op.drop_index("ix_lab_submissions_assignment_student", table_name="lab_submissions")
    op.drop_index("ix_lab_submissions_student",            table_name="lab_submissions")
    op.drop_index("ix_lab_submissions_assignment",         table_name="lab_submissions")
    op.drop_table("lab_submissions")

    op.drop_index("ix_lab_assignments_submission_type", table_name="lab_assignments")
    op.drop_index("ix_lab_assignments_status",          table_name="lab_assignments")
    op.drop_index("ix_lab_assignments_created_by",      table_name="lab_assignments")
    op.drop_index("ix_lab_assignments_syllabus",        table_name="lab_assignments")
    op.drop_table("lab_assignments")
