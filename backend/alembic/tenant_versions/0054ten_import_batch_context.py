"""tenant: add academic context columns to sis_import_batches — P1.4

Revision ID: 0054ten
Revises: 0053ten
Create Date: 2026-06-18

Summary of changes
------------------

ALTER sis_import_batches
    + program_id     UUID  NULL  — acad_programs.id at import time
    + program_name   TEXT  NULL  — denormalized display name
    + batch_id       UUID  NULL  — acad_batches.id at import time
    + batch_name     TEXT  NULL  — denormalized display name
    + semester_id    UUID  NULL  — acad_semesters.id at import time
    + semester_name  TEXT  NULL  — denormalized display name (label or "Semester N")
    + section_id     UUID  NULL  — acad_sections.id at import time
    + section_name   TEXT  NULL  — denormalized display name

All columns are nullable so existing import records remain valid (NULL values
render as "Unknown" in the UI — TASK 8 backward compatibility).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0054ten"
down_revision = "0053ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    for col in (
        sa.Column("program_id",    postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("program_name",  sa.String(200),                nullable=True),
        sa.Column("batch_id",      postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("batch_name",    sa.String(200),                nullable=True),
        sa.Column("semester_id",   postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("semester_name", sa.String(100),                nullable=True),
        sa.Column("section_id",    postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("section_name",  sa.String(50),                 nullable=True),
    ):
        op.add_column("sis_import_batches", col)


def downgrade() -> None:
    for col in (
        "section_name", "section_id",
        "semester_name", "semester_id",
        "batch_name", "batch_id",
        "program_name", "program_id",
    ):
        op.drop_column("sis_import_batches", col)
