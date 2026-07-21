"""tenant: preserve the evaluator's recommendation separately from the final mark

Revision ID: 0103ten
Revises: 0102ten
Create Date: 2026-07-21

The evaluator recommends; the assignment's owning faculty decides. Until now both
roles wrote the same column, so a faculty member who adjusted a mark destroyed the
evaluator's number and the recommendation could never be shown back or audited.

Two nullable columns on assignment_submissions:

  evaluator_marks_obtained  what the evaluator recommended
  evaluator_feedback        the evaluator's comments

`marks_obtained` / `feedback` keep their existing meaning — the AUTHORITATIVE
final grade — so everything already reading them (release, statistics,
count_ungraded, progress counts) is unaffected. The evaluator writes both its own
columns and the authoritative ones (their recommendation stands until reviewed);
the faculty owner writes only the authoritative ones, leaving the recommendation
intact for audit.

Purely additive and fully reversible. Existing rows get NULL, which reads
correctly as "no separate evaluator recommendation recorded" — those marks were
saved before this distinction existed, and nothing infers a value for them.
"""
import sqlalchemy as sa
from alembic import op

revision      = "0103ten"
down_revision = "0102ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "assignment_submissions",
        sa.Column("evaluator_marks_obtained", sa.Numeric(6, 2), nullable=True),
    )
    op.add_column(
        "assignment_submissions",
        sa.Column("evaluator_feedback", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("assignment_submissions", "evaluator_feedback")
    op.drop_column("assignment_submissions", "evaluator_marks_obtained")
