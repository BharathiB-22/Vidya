"""M09.5 Digital Exams Phase D — faculty subjective scoring columns.

Adds four columns to digital_exam_responses so faculty can record per-question
scores for subjective (non-MCQ) answers.  The DigitalAttemptStatus enum gains
FULLY_EVALUATED as a new varchar value; no DDL change is needed because the
column uses native_enum=False (stored as String).

Revision ID: 0046ten
Revises: 0045ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0046ten"
down_revision = "0045ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "digital_exam_responses",
        sa.Column("faculty_score",     sa.Numeric(6, 2),              nullable=True),
    )
    op.add_column(
        "digital_exam_responses",
        sa.Column("faculty_note",      sa.Text(),                     nullable=True),
    )
    op.add_column(
        "digital_exam_responses",
        sa.Column("faculty_scored_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "digital_exam_responses",
        sa.Column("faculty_scored_at", sa.DateTime(timezone=True),    nullable=True),
    )
    op.create_index(
        "ix_digital_responses_faculty_scored_by",
        "digital_exam_responses",
        ["faculty_scored_by"],
    )


def downgrade() -> None:
    op.drop_index("ix_digital_responses_faculty_scored_by", table_name="digital_exam_responses")
    op.drop_column("digital_exam_responses", "faculty_scored_at")
    op.drop_column("digital_exam_responses", "faculty_scored_by")
    op.drop_column("digital_exam_responses", "faculty_note")
    op.drop_column("digital_exam_responses", "faculty_score")
