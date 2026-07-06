"""tenant: add lab_group/program_number to lab_assignments, github_url to lab_submissions

Enables grouping a set of LabAssignment rows under one heading (e.g. "Python
Lab" -> "Program 1".."Program 10") and a GitHub-link submission option
alongside the existing file (content_url) and text (content_text) paths.
All columns nullable — fully backward compatible with existing rows/behavior.

Revision ID: 0069ten
Revises: 0068ten
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision      = "0069ten"
down_revision = "0068ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column("lab_assignments", sa.Column("lab_group", sa.String(), nullable=True))
    op.add_column("lab_assignments", sa.Column("program_number", sa.Integer(), nullable=True))
    op.create_index("ix_lab_assignments_lab_group", "lab_assignments", ["lab_group"])

    op.add_column("lab_submissions", sa.Column("github_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("lab_submissions", "github_url")

    op.drop_index("ix_lab_assignments_lab_group", table_name="lab_assignments")
    op.drop_column("lab_assignments", "program_number")
    op.drop_column("lab_assignments", "lab_group")
