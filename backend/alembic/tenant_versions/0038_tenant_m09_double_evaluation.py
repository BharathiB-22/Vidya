"""tenant: M09 double evaluation — new statuses + evaluation tracking columns

Revision ID: 0038ten
Revises: 0037ten
Create Date: 2026-06-09

Summary of changes
------------------

ALTER scanned_scripts
    + double_evaluation_enabled  BOOLEAN NOT NULL DEFAULT FALSE
          Denormalized from exam_papers.double_evaluation_enabled at ingest time.
          Avoids a cross-table join in every submit_marks() call.
    + primary_submitted_at       TIMESTAMPTZ NULL
          Timestamp when the primary evaluator submitted (Gate 1 on double-eval papers).
    + secondary_submitted_at     TIMESTAMPTZ NULL
          Timestamp when the secondary evaluator submitted.

ALTER exam_score_ledger
    + primary_total    NUMERIC(6,2) NULL
          Sum of primary evaluator_marks snapshotted at Board finalisation.
          NULL for single-evaluator papers.
    + secondary_total  NUMERIC(6,2) NULL
          Sum of secondary evaluator_marks snapshotted at Board finalisation.
          NULL for single-evaluator papers.

New ScriptStatus values (stored as VARCHAR; no PostgreSQL ENUM type):
    WAITING_SECOND_EVALUATOR — primary submitted; awaiting secondary
    SECONDARY_EVALUATED      — secondary submitted; auto-advances to MARKS_SUBMITTED
                               (preserved as a real state so M09.2 moderation can
                               insert a check between these two transitions)

Human-gate invariants (unchanged):
    No Celery task ever writes primary_submitted_at or secondary_submitted_at.
    No Celery task ever sets status to WAITING_SECOND_EVALUATOR, SECONDARY_EVALUATED,
    MARKS_SUBMITTED, or BOARD_FINALISED.
    exam_score_ledger primary_total / secondary_total are written ONLY by
    the board_finalise service method at Gate 2.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0038ten"
down_revision = "0037ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. scanned_scripts — double-eval tracking columns
    # ------------------------------------------------------------------
    op.add_column(
        "scanned_scripts",
        sa.Column(
            "double_evaluation_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "scanned_scripts",
        sa.Column("primary_submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "scanned_scripts",
        sa.Column("secondary_submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_scanned_scripts_double_eval",
        "scanned_scripts",
        ["double_evaluation_enabled"],
    )

    # ------------------------------------------------------------------
    # 2. exam_score_ledger — evaluator total snapshots
    # ------------------------------------------------------------------
    op.add_column(
        "exam_score_ledger",
        sa.Column("primary_total", sa.Numeric(6, 2), nullable=True),
    )
    op.add_column(
        "exam_score_ledger",
        sa.Column("secondary_total", sa.Numeric(6, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("exam_score_ledger", "secondary_total")
    op.drop_column("exam_score_ledger", "primary_total")

    op.drop_index("ix_scanned_scripts_double_eval", table_name="scanned_scripts")
    op.drop_column("scanned_scripts", "secondary_submitted_at")
    op.drop_column("scanned_scripts", "primary_submitted_at")
    op.drop_column("scanned_scripts", "double_evaluation_enabled")
