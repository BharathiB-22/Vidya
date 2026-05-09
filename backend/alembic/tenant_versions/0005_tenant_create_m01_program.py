"""tenant: create m01 program tables

Revision ID: 0005ten
Revises: 0004ten
Create Date: 2026-05-09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0005ten"
down_revision = "0004ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "programs",
        sa.Column("id",                  postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version",             sa.Integer(),                  nullable=False, server_default="1"),
        sa.Column("parent_version_id",   postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title",               sa.String(),                   nullable=False),
        sa.Column("degree_type",         sa.String(),                   nullable=False),
        sa.Column("department",          sa.String(),                   nullable=False),
        sa.Column("duration_years",      sa.Integer(),                  nullable=False),
        sa.Column("total_credits",       sa.Integer(),                  nullable=False),
        sa.Column("status",              sa.String(),                   nullable=False, server_default="DRAFT"),
        sa.Column("ai_model",            sa.String(),                   nullable=True),
        sa.Column("prompt_hash",         sa.String(),                   nullable=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at",         sa.DateTime(timezone=True),    nullable=True),
        sa.Column("created_by_user_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at",          sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",          sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["parent_version_id"], ["programs.id"]),
    )
    op.create_index("ix_programs_status",         "programs", ["status"])
    op.create_index("ix_programs_created_by",     "programs", ["created_by_user_id"])
    op.create_index("ix_programs_parent_version", "programs", ["parent_version_id"])
    op.create_index("ix_programs_created_at",     "programs", ["created_at"])

    op.create_table(
        "program_outcomes",
        sa.Column("id",            postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("program_id",    postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code",          sa.String(),                   nullable=False),
        sa.Column("description",   sa.Text(),                     nullable=False),
        sa.Column("bloom_level",   sa.String(),                   nullable=True),
        sa.Column("display_order", sa.Integer(),                  nullable=False, server_default="0"),
        sa.Column("created_at",    sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("program_id", "code"),
    )
    op.create_index("ix_program_outcomes_program", "program_outcomes", ["program_id"])

    op.create_table(
        "courses",
        sa.Column("id",              postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("program_id",      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code",            sa.String(),                   nullable=False),
        sa.Column("title",           sa.String(),                   nullable=False),
        sa.Column("credits",         sa.Integer(),                  nullable=False),
        sa.Column("semester",        sa.Integer(),                  nullable=False),
        sa.Column("is_elective",     sa.Boolean(),                  nullable=False, server_default="false"),
        sa.Column("is_ai_generated", sa.Boolean(),                  nullable=False, server_default="false"),
        sa.Column("hours_lecture",   sa.Integer(),                  nullable=True),
        sa.Column("hours_tutorial",  sa.Integer(),                  nullable=True),
        sa.Column("hours_practical", sa.Integer(),                  nullable=True),
        sa.Column("description",     sa.Text(),                     nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",      sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("program_id", "code"),
    )
    op.create_index("ix_courses_program",          "courses", ["program_id"])
    op.create_index("ix_courses_program_semester", "courses", ["program_id", "semester"])

    op.create_table(
        "course_prerequisites",
        sa.Column("id",                     postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("course_id",              postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prerequisite_course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"],              ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prerequisite_course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("course_id", "prerequisite_course_id"),
    )
    op.create_index("ix_course_prereqs_course",  "course_prerequisites", ["course_id"])
    op.create_index("ix_course_prereqs_prereq",  "course_prerequisites", ["prerequisite_course_id"])


def downgrade() -> None:
    op.drop_index("ix_course_prereqs_prereq",  table_name="course_prerequisites")
    op.drop_index("ix_course_prereqs_course",  table_name="course_prerequisites")
    op.drop_table("course_prerequisites")

    op.drop_index("ix_courses_program_semester", table_name="courses")
    op.drop_index("ix_courses_program",          table_name="courses")
    op.drop_table("courses")

    op.drop_index("ix_program_outcomes_program", table_name="program_outcomes")
    op.drop_table("program_outcomes")

    op.drop_index("ix_programs_created_at",     table_name="programs")
    op.drop_index("ix_programs_parent_version", table_name="programs")
    op.drop_index("ix_programs_created_by",     table_name="programs")
    op.drop_index("ix_programs_status",         table_name="programs")
    op.drop_table("programs")
