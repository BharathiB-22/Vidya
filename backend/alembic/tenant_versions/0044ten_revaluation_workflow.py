"""M09.3 Revaluation Workflow — sis_revaluation_requests + sis_revaluation_evaluations tables.

Post-publication revaluation: student applies → admin accepts → evaluator marks
→ Board ratifies → awarded_total = max(original, revaluation).

This is the ONLY legitimate post-publication mark change path.
The exam_score_ledger is append-only; ratification creates a new ledger note
rather than modifying existing rows (enforced in service layer).

Revision ID: 0044ten
Revises: 0043ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0044ten"
down_revision = "0043ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # sis_revaluation_requests
    op.create_table(
        "sis_revaluation_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "script_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scanned_scripts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("exam_paper_id",         postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_user_id",       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_roll_ref",      sa.String,                     nullable=True),
        sa.Column("original_total",        sa.Numeric(6, 2),              nullable=False),
        sa.Column("max_marks",             sa.Numeric(6, 2),              nullable=False),
        sa.Column("reason",                sa.Text,                       nullable=False),
        sa.Column("payment_reference",     sa.String,                     nullable=True),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="SUBMITTED",
        ),
        sa.Column("assigned_evaluator_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revaluation_total",     sa.Numeric(6, 2),              nullable=True),
        sa.Column("awarded_total",         sa.Numeric(6, 2),              nullable=True),
        sa.Column("admin_notes",           sa.Text,                       nullable=True),
        sa.Column("board_remarks",         sa.Text,                       nullable=True),
        sa.Column("decided_by",            postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at",            sa.DateTime(timezone=True),    nullable=True),
        sa.Column("window_closes_at",      sa.DateTime(timezone=True),    nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index("ix_reval_requests_script",     "sis_revaluation_requests", ["script_id"])
    op.create_index("ix_reval_requests_student",    "sis_revaluation_requests", ["student_user_id"])
    op.create_index("ix_reval_requests_exam_paper", "sis_revaluation_requests", ["exam_paper_id"])
    op.create_index("ix_reval_requests_status",     "sis_revaluation_requests", ["status"])
    op.create_index("ix_reval_requests_evaluator",  "sis_revaluation_requests", ["assigned_evaluator_id"])
    op.create_index("ix_reval_requests_created",    "sis_revaluation_requests", ["created_at"])

    # sis_revaluation_evaluations
    op.create_table(
        "sis_revaluation_evaluations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sis_revaluation_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question_id",       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_type",     sa.String(30),                 nullable=True),
        sa.Column("max_marks",         sa.Numeric(6, 2),              nullable=True),
        sa.Column("original_marks",    sa.Numeric(6, 2),              nullable=True),
        sa.Column("revaluation_marks", sa.Numeric(6, 2),              nullable=True),
        sa.Column("evaluator_note",    sa.Text,                       nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_reval_evals_request",  "sis_revaluation_evaluations", ["request_id"])
    op.create_index("ix_reval_evals_question", "sis_revaluation_evaluations", ["question_id"])


def downgrade() -> None:
    op.drop_index("ix_reval_evals_question", table_name="sis_revaluation_evaluations")
    op.drop_index("ix_reval_evals_request",  table_name="sis_revaluation_evaluations")
    op.drop_table("sis_revaluation_evaluations")

    op.drop_index("ix_reval_requests_created",    table_name="sis_revaluation_requests")
    op.drop_index("ix_reval_requests_evaluator",  table_name="sis_revaluation_requests")
    op.drop_index("ix_reval_requests_status",     table_name="sis_revaluation_requests")
    op.drop_index("ix_reval_requests_exam_paper", table_name="sis_revaluation_requests")
    op.drop_index("ix_reval_requests_student",    table_name="sis_revaluation_requests")
    op.drop_index("ix_reval_requests_script",     table_name="sis_revaluation_requests")
    op.drop_table("sis_revaluation_requests")
