"""Rename syllabus status values to reflect corrected governance model.

FACULTY_APPROVED → DEAN_APPROVED  (existing approved syllabi)
ADMIN_LOCKED     → DEAN_LOCKED

Revision ID: 0023ten
Revises: 0022ten
"""

from alembic import op

revision    = "0023ten"
down_revision = "0022ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute(
        "UPDATE syllabi SET status = 'DEAN_APPROVED' WHERE status = 'FACULTY_APPROVED'"
    )
    op.execute(
        "UPDATE syllabi SET status = 'DEAN_LOCKED' WHERE status = 'ADMIN_LOCKED'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE syllabi SET status = 'FACULTY_APPROVED' WHERE status = 'DEAN_APPROVED'"
    )
    op.execute(
        "UPDATE syllabi SET status = 'ADMIN_LOCKED' WHERE status = 'DEAN_LOCKED'"
    )
