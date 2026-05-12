"""tenant: create m03 course kit tables

Revision ID: 0007ten
Revises: 0006ten
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0007ten"
down_revision = "0006ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # 1. course_kits — references syllabi (M02) and self (parent_version_id)
    op.create_table(
        "course_kits",
        sa.Column("id",                   postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("syllabus_id",          postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_number",          sa.Integer(),                  nullable=False),
        sa.Column("version",              sa.Integer(),                  nullable=False, server_default="1"),
        sa.Column("parent_version_id",    postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status",              sa.String(),                   nullable=False, server_default="DRAFT"),
        sa.Column("complexity_level",    sa.String(),                   nullable=False, server_default="UG"),
        sa.Column("tone",                sa.String(),                   nullable=True),
        sa.Column("custom_instructions", sa.Text(),                     nullable=True),
        sa.Column("teaching_plan",       postgresql.JSONB(),             nullable=False, server_default="[]"),
        sa.Column("lesson_plans",        postgresql.JSONB(),             nullable=False, server_default="[]"),
        sa.Column("resources",           postgresql.JSONB(),             nullable=False, server_default="[]"),
        sa.Column("ai_model",            sa.String(),                   nullable=True),
        sa.Column("prompt_hash",         sa.String(),                   nullable=True),
        sa.Column("created_by_user_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_at",        sa.DateTime(timezone=True),    nullable=True),
        sa.Column("created_at",          sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",          sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["syllabus_id"],       ["syllabi.id"],      ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_version_id"], ["course_kits.id"]),
    )
    op.create_index("ix_course_kits_syllabus",       "course_kits", ["syllabus_id"])
    op.create_index("ix_course_kits_syllabus_unit",  "course_kits", ["syllabus_id", "unit_number"])
    op.create_index("ix_course_kits_status",         "course_kits", ["status"])
    op.create_index("ix_course_kits_created_by",     "course_kits", ["created_by_user_id"])
    op.create_index("ix_course_kits_parent_version", "course_kits", ["parent_version_id"])

    # 2. kit_slides — references course_kits
    op.create_table(
        "kit_slides",
        sa.Column("id",            postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kit_id",        postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slide_number",  sa.Integer(),                  nullable=False),
        sa.Column("title",         sa.String(),                   nullable=False),
        sa.Column("content",       postgresql.JSONB(),             nullable=False, server_default="{}"),
        sa.Column("speaker_notes", sa.Text(),                     nullable=True),
        sa.Column("bloom_level",   sa.String(),                   nullable=True),
        sa.Column("co_reference",  sa.String(),                   nullable=True),
        sa.Column("created_at",    sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",    sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["kit_id"], ["course_kits.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("kit_id", "slide_number"),
    )
    op.create_index("ix_kit_slides_kit", "kit_slides", ["kit_id"])

    # 3. kit_quizlets — references course_kits; answer_key is server-side only
    op.create_table(
        "kit_quizlets",
        sa.Column("id",                 postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kit_id",             postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_number",    sa.Integer(),                  nullable=False),
        sa.Column("question_text",      sa.Text(),                     nullable=False),
        sa.Column("question_type",      sa.String(),                   nullable=False, server_default="MCQ"),
        sa.Column("options",            postgresql.JSONB(),             nullable=False, server_default="[]"),
        sa.Column("answer_key",         postgresql.JSONB(),             nullable=False, server_default="{}"),
        sa.Column("answer_explanation", sa.Text(),                     nullable=True),
        sa.Column("bloom_level",        sa.String(),                   nullable=True),
        sa.Column("co_reference",       sa.String(),                   nullable=True),
        sa.Column("created_at",         sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",         sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["kit_id"], ["course_kits.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("kit_id", "question_number"),
    )
    op.create_index("ix_kit_quizlets_kit", "kit_quizlets", ["kit_id"])

    # 4. kit_assignments — references course_kits; model_answer is faculty-only
    op.create_table(
        "kit_assignments",
        sa.Column("id",                    postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kit_id",                postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_number",     sa.Integer(),                  nullable=False),
        sa.Column("title",                 sa.String(),                   nullable=False),
        sa.Column("assignment_type",       sa.String(),                   nullable=False, server_default="CLASSWORK"),
        sa.Column("question_text",         sa.Text(),                     nullable=False),
        sa.Column("complexity_level",      sa.String(),                   nullable=False, server_default="UG"),
        sa.Column("current_events_toggle", sa.Boolean(),                  nullable=False, server_default="false"),
        sa.Column("model_answer",          sa.Text(),                     nullable=True),
        sa.Column("rubric",                postgresql.JSONB(),             nullable=False, server_default="[]"),
        sa.Column("bloom_level",           sa.String(),                   nullable=True),
        sa.Column("co_reference",          sa.String(),                   nullable=True),
        sa.Column("created_at",            sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",            sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["kit_id"], ["course_kits.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("kit_id", "assignment_number"),
    )
    op.create_index("ix_kit_assignments_kit", "kit_assignments", ["kit_id"])


def downgrade() -> None:
    op.drop_index("ix_kit_assignments_kit", table_name="kit_assignments")
    op.drop_table("kit_assignments")

    op.drop_index("ix_kit_quizlets_kit", table_name="kit_quizlets")
    op.drop_table("kit_quizlets")

    op.drop_index("ix_kit_slides_kit", table_name="kit_slides")
    op.drop_table("kit_slides")

    op.drop_index("ix_course_kits_parent_version", table_name="course_kits")
    op.drop_index("ix_course_kits_created_by",     table_name="course_kits")
    op.drop_index("ix_course_kits_status",         table_name="course_kits")
    op.drop_index("ix_course_kits_syllabus_unit",  table_name="course_kits")
    op.drop_index("ix_course_kits_syllabus",       table_name="course_kits")
    op.drop_table("course_kits")
