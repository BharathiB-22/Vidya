"""M09.7 OCR Review Queue — ocr_review_queue + ocr_threshold_config.

Creates two tenant-schema tables for the human OCR review workflow:
  ocr_review_queue      — queue of scripts needing human OCR review, ordered by priority
  ocr_threshold_config  — configurable OCR confidence thresholds (global + exam overrides)

Revision ID: 0049ten
Revises: 0048ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0049ten"
down_revision = "0048ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # ocr_threshold_config — must exist before queue (no FK, but logical)
    # ------------------------------------------------------------------
    op.create_table(
        "ocr_threshold_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("scope",                       sa.String(20),           nullable=False),
        sa.Column("scope_ref_id",                postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("low_confidence_threshold",    sa.Numeric(4, 3),        nullable=False,
                  server_default="0.600"),
        sa.Column("medium_confidence_threshold", sa.Numeric(4, 3),        nullable=False,
                  server_default="0.800"),
        sa.Column("is_active",    sa.Boolean(),                           nullable=False,
                  server_default="true"),
        sa.Column("created_by",   postgresql.UUID(as_uuid=True),          nullable=False),
        sa.Column("created_at",   sa.DateTime(timezone=True),             nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",   sa.DateTime(timezone=True),             nullable=True),
        sa.UniqueConstraint("scope", "scope_ref_id", name="uq_ocr_threshold_scope_ref"),
    )
    op.create_index("ix_ocr_threshold_scope",  "ocr_threshold_config", ["scope"])
    op.create_index("ix_ocr_threshold_ref",    "ocr_threshold_config", ["scope_ref_id"])
    op.create_index("ix_ocr_threshold_active", "ocr_threshold_config", ["is_active"])

    # Seed the global default row so every tenant has a threshold from day 1.
    op.execute(
        """
        INSERT INTO ocr_threshold_config
            (id, scope, scope_ref_id, low_confidence_threshold,
             medium_confidence_threshold, is_active, created_by)
        VALUES
            (gen_random_uuid(), 'GLOBAL', NULL, 0.600, 0.800, true,
             '00000000-0000-0000-0000-000000000000')
        ON CONFLICT (scope, scope_ref_id) DO NOTHING;
        """
    )

    # ------------------------------------------------------------------
    # ocr_review_queue
    # ------------------------------------------------------------------
    op.create_table(
        "ocr_review_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("script_id",            postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exam_paper_id",        postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("priority_category",    sa.String(30),                 nullable=False),
        sa.Column("priority_score",       sa.Integer(),                  nullable=False),
        sa.Column("ocr_confidence",       sa.Numeric(4, 3),              nullable=True),
        sa.Column("original_ocr_text",    sa.Text(),                     nullable=True),
        sa.Column("review_status",        sa.String(30),                 nullable=False,
                  server_default="PENDING"),
        sa.Column("assigned_reviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_started_at",    sa.DateTime(timezone=True),    nullable=True),
        sa.Column("corrected_text",       sa.Text(),                     nullable=True),
        sa.Column("reviewer_notes",       sa.Text(),                     nullable=True),
        sa.Column("action_taken",         sa.String(30),                 nullable=True),
        sa.Column("completed_by",         postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_at",         sa.DateTime(timezone=True),    nullable=True),
        sa.Column("created_at",           sa.DateTime(timezone=True),    nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",           sa.DateTime(timezone=True),    nullable=True),
    )
    op.create_index("ix_ocr_queue_script",   "ocr_review_queue", ["script_id"])
    op.create_index("ix_ocr_queue_paper",    "ocr_review_queue", ["exam_paper_id"])
    op.create_index("ix_ocr_queue_status",   "ocr_review_queue", ["review_status"])
    op.create_index("ix_ocr_queue_priority", "ocr_review_queue", ["priority_score"])
    op.create_index("ix_ocr_queue_category", "ocr_review_queue", ["priority_category"])
    op.create_index("ix_ocr_queue_reviewer", "ocr_review_queue", ["assigned_reviewer_id"])
    op.create_index("ix_ocr_queue_created",  "ocr_review_queue", ["created_at"])


def downgrade() -> None:
    op.drop_table("ocr_review_queue")
    op.drop_table("ocr_threshold_config")
