"""tenant: coursework evaluator workflow (P1.17)

Revision ID: 0096ten
Revises: 0095ten
Create Date: 2026-07-16

Coursework assignments had no evaluation hand-off: faculty published an
assignment, students submitted, and whoever held FACULTY graded it. The real
workflow routes evaluation through the department:

    Faculty creates -> Faculty submits -> Dept/Admin assigns Evaluator
    -> Evaluator evaluates -> Marks finalized

Evaluator allocation itself reuses the existing M09.6 assignment engine
(evaluation_assignments, target_entity='assignment_submission') and the existing
EVALUATOR role, so nothing new is created for that here.

What this migration adds is the assignment's own side of the hand-off:

    assignments.submitted_at / submitted_by_user_id   faculty -> department
    assignments.finalized_at / finalized_by_user_id   the human ratification of
                                                      the marks, recorded at the
                                                      database level

status gains SUBMITTED and FINALIZED. That column is an unconstrained VARCHAR
holding an application-side enum, so the two new values need no type surgery. All
columns here are additive and nullable; existing rows keep their status and read
as never-submitted, never-finalized.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0096ten"
down_revision = "0095ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column("assignments", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assignments", sa.Column("submitted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("assignments", sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assignments", sa.Column("finalized_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column("assignments", "finalized_by_user_id")
    op.drop_column("assignments", "finalized_at")
    op.drop_column("assignments", "submitted_by_user_id")
    op.drop_column("assignments", "submitted_at")
