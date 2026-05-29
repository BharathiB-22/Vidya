"""tenant: create subject_assignments table (H-31 Faculty Assignment Foundation)

Revision ID: 0022ten
Revises: 0021ten
Create Date: 2026-05-28

Creates subject_assignments which records faculty ownership of a course in a
given semester.  History is immutable: revocation sets is_active=False and
stamps revoked_at rather than deleting the row.

Constraints enforced at service layer (not DB-level partial index):
  - at most one active PRIMARY per (course_id, semester_id)
  - a faculty member may not be assigned twice to the same course+semester

FKs:
  course_id   → courses.id        (m01 program advisor — same tenant schema)
  semester_id → acad_semesters.id (m_academics          — same tenant schema)

No FK on faculty_user_id / assigned_by / revoked_by — consistent with the
rest of the codebase where user IDs are stored as plain UUIDs to avoid
cascade coupling with the users table.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision      = "0022ten"
down_revision = "0021ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "subject_assignments",
        sa.Column("id",                  UUID(as_uuid=True), primary_key=True),
        sa.Column("course_id",           UUID(as_uuid=True),
                  sa.ForeignKey("courses.id",        ondelete="CASCADE"), nullable=False),
        sa.Column("faculty_user_id",     UUID(as_uuid=True), nullable=False),
        sa.Column("semester_id",         UUID(as_uuid=True),
                  sa.ForeignKey("acad_semesters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_by_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_at",         sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("is_active",           sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("role_in_course",      sa.String(20), nullable=False),
        sa.Column("revoked_at",          sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id",  UUID(as_uuid=True), nullable=True),
    )

    op.create_index(
        "ix_subject_assignments_course_sem",
        "subject_assignments",
        ["course_id", "semester_id"],
    )
    op.create_index(
        "ix_subject_assignments_faculty",
        "subject_assignments",
        ["faculty_user_id", "is_active"],
    )
    op.create_index(
        "ix_subject_assignments_active",
        "subject_assignments",
        ["is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_subject_assignments_active",     table_name="subject_assignments")
    op.drop_index("ix_subject_assignments_faculty",    table_name="subject_assignments")
    op.drop_index("ix_subject_assignments_course_sem", table_name="subject_assignments")
    op.drop_table("subject_assignments")
