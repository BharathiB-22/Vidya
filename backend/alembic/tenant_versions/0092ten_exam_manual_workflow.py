"""tenant: manual paper builder + workflow (P1.16)

Revision ID: 0092ten
Revises: 0091ten
Create Date: 2026-07-16

Two additive columns for the offline Question Paper workflow redesign (m08):

    exam_papers.creation_mode    "AI" (Celery/LLM generation, the existing path)
                                 or "MANUAL" (empty paper, questions added by
                                 hand). Existing rows are all AI generations, so
                                 the server default backfills them to "AI".

    exam_questions.display_order explicit ordering for the manual builder's
                                 drag-&-drop. Backfilled per paper from the
                                 previous implicit order (created_at within a
                                 section), so existing papers keep their order.

No enum migration: exam paper/question statuses are stored as VARCHAR
(native_enum=False), so the new Dean-review reuse of BOARD_APPROVED /
BOARD_RETURNED needs no schema change.
"""
import sqlalchemy as sa
from alembic import op

revision      = "0092ten"
down_revision = "0091ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "exam_papers",
        sa.Column("creation_mode", sa.String(), nullable=False, server_default="AI"),
    )
    op.add_column(
        "exam_questions",
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    )
    # Backfill display_order per paper from the prior implicit ordering.
    op.execute(
        """
        UPDATE exam_questions q
        SET display_order = sub.rn - 1
        FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY exam_paper_id
                       ORDER BY section_label NULLS FIRST, created_at
                   ) AS rn
            FROM exam_questions
        ) sub
        WHERE q.id = sub.id
        """
    )


def downgrade() -> None:
    op.drop_column("exam_questions", "display_order")
    op.drop_column("exam_papers", "creation_mode")
