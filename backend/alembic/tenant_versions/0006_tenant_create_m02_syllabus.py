"""tenant: create m02 syllabus tables

Revision ID: 0006ten
Revises: 0005ten
Create Date: 2026-05-09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0006ten"
down_revision = "0005ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # 1. syllabi — references courses (M01) and self (parent_version_id)
    op.create_table(
        "syllabi",
        sa.Column("id",                  postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("course_id",           postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version",             sa.Integer(),                  nullable=False, server_default="1"),
        sa.Column("parent_version_id",   postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status",              sa.String(),                   nullable=False, server_default="DRAFT"),
        sa.Column("custom_instructions", sa.Text(),                     nullable=True),
        sa.Column("change_note",         sa.Text(),                     nullable=True),
        sa.Column("ai_model",            sa.String(),                   nullable=True),
        sa.Column("prompt_hash",         sa.String(),                   nullable=True),
        sa.Column("created_by_user_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at",         sa.DateTime(timezone=True),    nullable=True),
        sa.Column("locked_by_user_id",   postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("locked_at",           sa.DateTime(timezone=True),    nullable=True),
        sa.Column("created_at",          sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",          sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["course_id"],         ["courses.id"],  ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_version_id"], ["syllabi.id"]),
    )
    op.create_index("ix_syllabi_course",         "syllabi", ["course_id"])
    op.create_index("ix_syllabi_course_version", "syllabi", ["course_id", "version"])
    op.create_index("ix_syllabi_status",         "syllabi", ["status"])
    op.create_index("ix_syllabi_created_by",     "syllabi", ["created_by_user_id"])
    op.create_index("ix_syllabi_parent_version", "syllabi", ["parent_version_id"])

    # 2. course_outcomes — references syllabi
    op.create_table(
        "course_outcomes",
        sa.Column("id",            postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("syllabus_id",   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code",          sa.String(),                   nullable=False),
        sa.Column("description",   sa.Text(),                     nullable=False),
        sa.Column("bloom_level",   sa.String(),                   nullable=False),
        sa.Column("display_order", sa.Integer(),                  nullable=False, server_default="0"),
        sa.Column("created_at",    sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",    sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["syllabus_id"], ["syllabi.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("syllabus_id", "code"),
    )
    op.create_index("ix_course_outcomes_syllabus", "course_outcomes", ["syllabus_id"])

    # 3. co_po_mappings — references course_outcomes + program_outcomes (M01)
    op.create_table(
        "co_po_mappings",
        sa.Column("id",               postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("co_id",            postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("po_id",            postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mapping_strength", sa.String(),                   nullable=False, server_default="MEDIUM"),
        sa.Column("justification",    sa.Text(),                     nullable=True),
        sa.Column("created_at",       sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["co_id"], ["course_outcomes.id"],  ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["po_id"], ["program_outcomes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("co_id", "po_id"),
    )
    op.create_index("ix_co_po_mappings_co", "co_po_mappings", ["co_id"])
    op.create_index("ix_co_po_mappings_po", "co_po_mappings", ["po_id"])

    # 4. syllabus_units — references syllabi
    op.create_table(
        "syllabus_units",
        sa.Column("id",            postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("syllabus_id",   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_number",   sa.Integer(),                  nullable=False),
        sa.Column("title",         sa.String(),                   nullable=False),
        sa.Column("topics",        postgresql.JSONB(),             nullable=False, server_default="[]"),
        sa.Column("total_hours",   sa.Integer(),                  nullable=False),
        sa.Column("pedagogy",      sa.String(),                   nullable=True),
        sa.Column("bloom_summary", postgresql.JSONB(),             nullable=True),
        sa.Column("created_at",    sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",    sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["syllabus_id"], ["syllabi.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("syllabus_id", "unit_number"),
    )
    op.create_index("ix_syllabus_units_syllabus", "syllabus_units", ["syllabus_id"])

    # 5. syllabus_references — references syllabi
    op.create_table(
        "syllabus_references",
        sa.Column("id",           postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("syllabus_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title",        sa.Text(),                     nullable=False),
        sa.Column("authors",      postgresql.JSONB(),             nullable=False, server_default="[]"),
        sa.Column("year",         sa.Integer(),                  nullable=True),
        sa.Column("ref_type",     sa.String(),                   nullable=False, server_default="TEXTBOOK"),
        sa.Column("source",       sa.String(),                   nullable=False, server_default="MANUAL"),
        sa.Column("doi",          sa.String(),                   nullable=True),
        sa.Column("isbn",         sa.String(),                   nullable=True),
        sa.Column("url",          sa.Text(),                     nullable=True),
        sa.Column("publisher",    sa.String(),                   nullable=True),
        sa.Column("is_confirmed", sa.Boolean(),                  nullable=False, server_default="true"),
        sa.Column("created_at",   sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",   sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["syllabus_id"], ["syllabi.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_syllabus_references_syllabus", "syllabus_references", ["syllabus_id"])
    op.create_index("ix_syllabus_references_source",   "syllabus_references", ["source"])


def downgrade() -> None:
    op.drop_index("ix_syllabus_references_source",   table_name="syllabus_references")
    op.drop_index("ix_syllabus_references_syllabus", table_name="syllabus_references")
    op.drop_table("syllabus_references")

    op.drop_index("ix_syllabus_units_syllabus", table_name="syllabus_units")
    op.drop_table("syllabus_units")

    op.drop_index("ix_co_po_mappings_po", table_name="co_po_mappings")
    op.drop_index("ix_co_po_mappings_co", table_name="co_po_mappings")
    op.drop_table("co_po_mappings")

    op.drop_index("ix_course_outcomes_syllabus", table_name="course_outcomes")
    op.drop_table("course_outcomes")

    op.drop_index("ix_syllabi_parent_version", table_name="syllabi")
    op.drop_index("ix_syllabi_created_by",     table_name="syllabi")
    op.drop_index("ix_syllabi_status",         table_name="syllabi")
    op.drop_index("ix_syllabi_course_version", table_name="syllabi")
    op.drop_index("ix_syllabi_course",         table_name="syllabi")
    op.drop_table("syllabi")
