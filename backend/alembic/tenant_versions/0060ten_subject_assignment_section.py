"""subject_assignments — add nullable section_id FK.

A subject assignment now optionally tracks which section the faculty
teaches.  Nullable so existing rows are unaffected; the application
enforces the value going forward via the assignment creation workflow.

Revision ID: 0060ten
Revises: 0059ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0060ten"
down_revision = "0059ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "subject_assignments",
        sa.Column(
            "section_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acad_sections.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_subject_assignments_section_id",
        "subject_assignments",
        ["section_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_subject_assignments_section_id", table_name="subject_assignments")
    op.drop_column("subject_assignments", "section_id")
