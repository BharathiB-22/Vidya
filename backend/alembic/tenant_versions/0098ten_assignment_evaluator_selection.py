"""tenant: faculty evaluator selection on an assignment (P1.19)

Revision ID: 0098ten
Revises: 0097ten
Create Date: 2026-07-16

Faculty had no way to say who should evaluate the coursework they set. 0096ten
gave the assignment its hand-off to the department, and allocation itself already
reuses the M09.6 assignment engine — but every allocation had to be made by hand,
one submission at a time, after the fact. The evaluator the faculty had in mind
when they wrote the assignment was never recorded anywhere.

This adds exactly that, and nothing else:

    assignments.evaluator_user_ids   the evaluator(s) the faculty nominated when
                                     creating the assignment. NULL/[] = nobody
                                     nominated, which is the pre-existing
                                     behaviour: the department allocates by hand.

When a student submits, one work item per submission is created against the
nominated evaluators, round-robin, through the SAME M09.6 engine
(evaluation_assignments, target_entity='assignment_submission'). No second
ledger, no new role, no duplicated allocation logic — the only new thing is that
the nomination is remembered, so the work item can be created the moment there is
work rather than waiting for a human to repeat a decision already made.

Additive and nullable: existing assignments read as "nobody nominated" and keep
their current manual-allocation flow untouched.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0098ten"
down_revision = "0097ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "assignments",
        sa.Column("evaluator_user_ids", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("assignments", "evaluator_user_ids")
