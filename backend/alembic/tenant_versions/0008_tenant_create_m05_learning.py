"""tenant: create m05 learning material packager tables

Revision ID: 0008ten
Revises: 0007ten
Create Date: 2026-05-15

Tables created (tenant schema):
  learning_packages    — one package per (syllabus_id, unit_number), versioned
  package_items        — curated/faculty material items; content_hash for dedup
  package_qa_sessions  — per-student Q&A conversation
  package_qa_messages  — individual turns; sources JSONB for RAG citations
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0008ten"
down_revision = "0007ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # 1. learning_packages — references syllabi (M02)
    op.create_table(
        "learning_packages",
        sa.Column("id",                 postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("syllabus_id",        postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_number",        sa.Integer(),                  nullable=False),
        sa.Column("version",            sa.Integer(),                  nullable=False, server_default="1"),
        sa.Column("status",             sa.String(),                   nullable=False, server_default="PENDING"),
        sa.Column("top_n",              sa.Integer(),                  nullable=False, server_default="10"),
        sa.Column("item_count",         sa.Integer(),                  nullable=False, server_default="0"),
        sa.Column("qdrant_indexed",     sa.Boolean(),                  nullable=False, server_default="false"),
        sa.Column("ai_model",           sa.String(),                   nullable=True),
        sa.Column("prompt_hash",        sa.String(),                   nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("curated_at",         sa.DateTime(timezone=True),    nullable=True),
        sa.Column("created_at",         sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",         sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["syllabus_id"], ["syllabi.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_learning_packages_syllabus",      "learning_packages", ["syllabus_id"])
    op.create_index("ix_learning_packages_syllabus_unit", "learning_packages", ["syllabus_id", "unit_number"])
    op.create_index("ix_learning_packages_status",        "learning_packages", ["status"])
    op.create_index("ix_learning_packages_created_by",    "learning_packages", ["created_by_user_id"])

    # 2. package_items — references learning_packages
    op.create_table(
        "package_items",
        sa.Column("id",                  postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("package_id",          postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type",         sa.String(),                   nullable=False),
        sa.Column("title",               sa.String(),                   nullable=False),
        sa.Column("url",                 sa.String(),                   nullable=True),
        # SHA-256(normalize(url) + title + text_checksum) — used for dedup and diff
        sa.Column("content_hash",        sa.String(),                   nullable=True),
        sa.Column("metadata",            postgresql.JSONB(),             nullable=False, server_default="{}"),
        sa.Column("relevance_score",     sa.Float(),                    nullable=True),
        sa.Column("faculty_recommended", sa.Boolean(),                  nullable=False, server_default="false"),
        sa.Column("added_by_user_id",    postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("display_order",       sa.Integer(),                  nullable=False, server_default="0"),
        sa.Column("qdrant_indexed",      sa.Boolean(),                  nullable=False, server_default="false"),
        sa.Column("created_at",          sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",          sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["package_id"], ["learning_packages.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_package_items_package",      "package_items", ["package_id"])
    op.create_index("ix_package_items_source_type",  "package_items", ["source_type"])
    op.create_index("ix_package_items_content_hash", "package_items", ["package_id", "content_hash"])
    op.create_index("ix_package_items_recommended",  "package_items", ["package_id", "faculty_recommended"])

    # 3. package_qa_sessions — references learning_packages
    op.create_table(
        "package_qa_sessions",
        sa.Column("id",              postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("package_id",      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at",      sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",      sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["package_id"], ["learning_packages.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_package_qa_sessions_package", "package_qa_sessions", ["package_id"])
    op.create_index("ix_package_qa_sessions_student", "package_qa_sessions", ["package_id", "student_user_id"])

    # 4. package_qa_messages — references package_qa_sessions
    op.create_table(
        "package_qa_messages",
        sa.Column("id",         postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role",       sa.String(),                   nullable=False),
        sa.Column("content",    sa.Text(),                     nullable=False),
        # [{item_id, title, url, snippet, relevance_score}]
        sa.Column("sources",    postgresql.JSONB(),             nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["session_id"], ["package_qa_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_package_qa_messages_session",    "package_qa_messages", ["session_id"])
    op.create_index("ix_package_qa_messages_session_ts", "package_qa_messages", ["session_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_package_qa_messages_session_ts", table_name="package_qa_messages")
    op.drop_index("ix_package_qa_messages_session",    table_name="package_qa_messages")
    op.drop_table("package_qa_messages")

    op.drop_index("ix_package_qa_sessions_student", table_name="package_qa_sessions")
    op.drop_index("ix_package_qa_sessions_package", table_name="package_qa_sessions")
    op.drop_table("package_qa_sessions")

    op.drop_index("ix_package_items_recommended",  table_name="package_items")
    op.drop_index("ix_package_items_content_hash", table_name="package_items")
    op.drop_index("ix_package_items_source_type",  table_name="package_items")
    op.drop_index("ix_package_items_package",      table_name="package_items")
    op.drop_table("package_items")

    op.drop_index("ix_learning_packages_created_by",    table_name="learning_packages")
    op.drop_index("ix_learning_packages_status",        table_name="learning_packages")
    op.drop_index("ix_learning_packages_syllabus_unit", table_name="learning_packages")
    op.drop_index("ix_learning_packages_syllabus",      table_name="learning_packages")
    op.drop_table("learning_packages")
