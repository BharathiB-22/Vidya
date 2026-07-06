"""tenant: create m04 assignments tables (theory/coursework, separate from M06 Labs)

Tables created (tenant schema):
  assignments             — faculty-created assignments (essay/case study/report/homework)
  assignment_submissions  — one or more per student per assignment (attempts)

Revision ID: 0068ten
Revises: 0067ten
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0068ten"
down_revision = "0067ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "assignments",
        sa.Column("id",                   postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("syllabus_id",          postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id",   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title",                sa.String(),                   nullable=False),
        sa.Column("description",          sa.Text(),                     nullable=True),
        sa.Column("instructions",         sa.Text(),                     nullable=True),
        sa.Column("assignment_type",      sa.String(),                   nullable=False, server_default="HOMEWORK"),
        sa.Column("max_marks",            sa.Numeric(6, 2),              nullable=False),
        sa.Column("weightage_percent",    sa.Numeric(5, 2),              nullable=True),
        sa.Column("due_date",             sa.DateTime(timezone=True),    nullable=True),
        sa.Column("allow_late",           sa.Boolean(),                  nullable=False, server_default="true"),
        sa.Column("late_penalty_percent", sa.Numeric(5, 2),              nullable=True),
        sa.Column("max_attempts",         sa.Integer(),                  nullable=False, server_default="1"),
        sa.Column("allowed_file_types",   postgresql.JSONB(),            nullable=False, server_default="[]"),
        sa.Column("status",               sa.String(),                   nullable=False, server_default="DRAFT"),
        sa.Column("published_at",         sa.DateTime(timezone=True),    nullable=True),
        sa.Column("closed_at",            sa.DateTime(timezone=True),    nullable=True),
        sa.Column("created_at",           sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",           sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["syllabus_id"], ["syllabi.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_assignments_syllabus",   "assignments", ["syllabus_id"])
    op.create_index("ix_assignments_created_by", "assignments", ["created_by_user_id"])
    op.create_index("ix_assignments_status",     "assignments", ["status"])

    op.create_table(
        "assignment_submissions",
        sa.Column("id",                postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_user_id",   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number",    sa.Integer(),                  nullable=False, server_default="1"),
        sa.Column("content_url",       sa.String(),                   nullable=True),
        sa.Column("content_text",      sa.Text(),                     nullable=True),
        sa.Column("submitted_at",      sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("is_late",           sa.Boolean(),                  nullable=False, server_default="false"),
        sa.Column("status",            sa.String(),                   nullable=False, server_default="SUBMITTED"),
        sa.Column("marks_obtained",    sa.Numeric(6, 2),              nullable=True),
        sa.Column("feedback",          sa.Text(),                     nullable=True),
        sa.Column("graded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("graded_at",         sa.DateTime(timezone=True),    nullable=True),
        sa.Column("returned_at",       sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("assignment_id", "student_user_id", "attempt_number",
                             name="uq_assignment_submissions_attempt"),
    )
    op.create_index("ix_assignment_submissions_assignment",         "assignment_submissions", ["assignment_id"])
    op.create_index("ix_assignment_submissions_student",            "assignment_submissions", ["student_user_id"])
    op.create_index("ix_assignment_submissions_assignment_student", "assignment_submissions", ["assignment_id", "student_user_id"])
    op.create_index("ix_assignment_submissions_status",             "assignment_submissions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_assignment_submissions_status",             table_name="assignment_submissions")
    op.drop_index("ix_assignment_submissions_assignment_student", table_name="assignment_submissions")
    op.drop_index("ix_assignment_submissions_student",            table_name="assignment_submissions")
    op.drop_index("ix_assignment_submissions_assignment",         table_name="assignment_submissions")
    op.drop_table("assignment_submissions")

    op.drop_index("ix_assignments_status",     table_name="assignments")
    op.drop_index("ix_assignments_created_by", table_name="assignments")
    op.drop_index("ix_assignments_syllabus",   table_name="assignments")
    op.drop_table("assignments")
