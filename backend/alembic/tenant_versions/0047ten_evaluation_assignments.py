"""M09.6 Assignment Engine — evaluation_assignments table.

A unified ledger of evaluation work allocated to faculty/evaluators across all
evaluation workflows (REGULAR, DOUBLE_EVALUATION, MODERATION, REVALUATION,
DIGITAL_SUBJECTIVE).

Stores only anonymous work-item references (script_code / attempt_code) — never
student identity.  Reassignment is modelled as a chain (reassigned_from /
reassigned_to) so the full audit trail is preserved.  A partial unique index
guarantees at most one ACTIVE assignment per (target_entity, target_id,
evaluation_round).

Revision ID: 0047ten
Revises: 0046ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0047ten"
down_revision = "0046ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "evaluation_assignments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("assignment_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ASSIGNED"),
        sa.Column("target_entity", sa.String(40), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exam_paper_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluation_round", sa.String(20), nullable=False, server_default="NONE"),
        sa.Column("script_code", sa.String, nullable=True),
        sa.Column("attempt_code", sa.String, nullable=True),
        sa.Column("evaluator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "assigned_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reassigned_from",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evaluation_assignments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reassigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reassign_reason", sa.Text, nullable=True),
        sa.Column("cancel_reason", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_eval_assignments_evaluator",   "evaluation_assignments", ["evaluator_id"])
    op.create_index("ix_eval_assignments_status",      "evaluation_assignments", ["status"])
    op.create_index("ix_eval_assignments_type",        "evaluation_assignments", ["assignment_type"])
    op.create_index("ix_eval_assignments_target",      "evaluation_assignments", ["target_entity", "target_id"])
    op.create_index("ix_eval_assignments_exam_paper",  "evaluation_assignments", ["exam_paper_id"])
    op.create_index("ix_eval_assignments_assigned_by", "evaluation_assignments", ["assigned_by"])
    op.create_index("ix_eval_assignments_created",     "evaluation_assignments", ["created_at"])

    # Primary duplicate guard: only one ACTIVE assignment per work item + round.
    op.create_index(
        "uq_eval_assignments_active_target",
        "evaluation_assignments",
        ["target_entity", "target_id", "evaluation_round"],
        unique=True,
        postgresql_where=sa.text("status IN ('ASSIGNED','IN_PROGRESS','SUBMITTED')"),
    )


def downgrade() -> None:
    op.drop_index("uq_eval_assignments_active_target", table_name="evaluation_assignments")
    op.drop_index("ix_eval_assignments_created",     table_name="evaluation_assignments")
    op.drop_index("ix_eval_assignments_assigned_by", table_name="evaluation_assignments")
    op.drop_index("ix_eval_assignments_exam_paper",  table_name="evaluation_assignments")
    op.drop_index("ix_eval_assignments_target",      table_name="evaluation_assignments")
    op.drop_index("ix_eval_assignments_type",        table_name="evaluation_assignments")
    op.drop_index("ix_eval_assignments_status",      table_name="evaluation_assignments")
    op.drop_index("ix_eval_assignments_evaluator",   table_name="evaluation_assignments")
    op.drop_table("evaluation_assignments")
