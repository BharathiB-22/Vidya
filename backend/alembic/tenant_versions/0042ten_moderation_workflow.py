"""M09.2 Moderation Workflow — script_moderation_reviews table.

Adds MODERATION_PENDING / MODERATION_COMPLETE as new ScriptStatus values
(stored as VARCHAR — no enum DDL change required).

New table: script_moderation_reviews
  One row per moderation event per scanned script.
  Created when evaluator variance exceeds the paper's discrepancy_threshold_pct
  (auto-flag) or when a Dean/Admin manually flags a MARKS_SUBMITTED script.

No changes to exam_papers: discrepancy_threshold_pct already added in 0038ten.

Revision ID: 0042ten
Revises: 0041ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0042ten"
down_revision = "0041ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "script_moderation_reviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "script_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scanned_scripts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("exam_paper_id",      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("primary_total",      sa.Numeric(6, 2), nullable=False),
        sa.Column("secondary_total",    sa.Numeric(6, 2), nullable=False),
        sa.Column("variance_pct",       sa.Numeric(5, 2), nullable=False),
        sa.Column("variance_threshold", sa.Numeric(5, 2), nullable=False),
        sa.Column("flag_reason",        sa.Text,          nullable=False),
        # NULL = auto-flagged by system; non-NULL = named human
        sa.Column("flagged_by",         postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "flagged_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("moderator_id",       postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("moderation_notes",   sa.Text,          nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("completed_at",  sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_moderation_reviews_script",
        "script_moderation_reviews",
        ["script_id"],
    )
    op.create_index(
        "ix_moderation_reviews_exam_paper",
        "script_moderation_reviews",
        ["exam_paper_id"],
    )
    op.create_index(
        "ix_moderation_reviews_status",
        "script_moderation_reviews",
        ["status"],
    )
    op.create_index(
        "ix_moderation_reviews_moderator",
        "script_moderation_reviews",
        ["moderator_id"],
    )
    op.create_index(
        "ix_moderation_reviews_created",
        "script_moderation_reviews",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_moderation_reviews_created",    table_name="script_moderation_reviews")
    op.drop_index("ix_moderation_reviews_moderator",  table_name="script_moderation_reviews")
    op.drop_index("ix_moderation_reviews_status",     table_name="script_moderation_reviews")
    op.drop_index("ix_moderation_reviews_exam_paper", table_name="script_moderation_reviews")
    op.drop_index("ix_moderation_reviews_script",     table_name="script_moderation_reviews")
    op.drop_table("script_moderation_reviews")
