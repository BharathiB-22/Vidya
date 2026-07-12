"""tenant: attendance sessions may belong to an elective group, not a section

Revision ID: 0080ten
Revises: 0079ten
Create Date: 2026-07-10

An elective is not taken by a section. If MCA-A contributes 20 students and MCA-B
contributes 15, the faculty teaching that elective has ONE class of 35 — they must
mark attendance once, not twice against two section rosters that each hide half
the class.

So a session's class is now one of two things:

    section_id IS NOT NULL   a regular course taught to one section
    section_id IS NULL       an elective group: everyone in `semester_id` who
                             registered for `course_id`

`semester_id` is added because it becomes load-bearing. Today the term is only
reachable by walking section -> semester; drop the section and the session no
longer knows which term it belongs to. It is backfilled from the section every
existing row already has, so no historical row changes meaning.

The single unique constraint is replaced by two partial ones. A plain unique over
(course, section, date, period) would not constrain elective sessions at all,
because Postgres treats every NULL section as distinct and would happily accept
the same elective period twice.

Historical rows are NOT rewritten. A tenant that already marked an elective
per-section keeps those sessions exactly as they were; only newly created
sessions use the elective group. The migration is additive.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision      = "0080ten"
down_revision = "0079ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # 1. The term must be knowable without a section.
    op.add_column(
        "sis_attendance_sessions",
        sa.Column("semester_id", UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE sis_attendance_sessions s
        SET semester_id = sec.semester_id
        FROM acad_sections sec
        WHERE sec.id = s.section_id
        """
    )
    # Every existing row has a NOT NULL section_id, so every row is now populated.
    op.alter_column("sis_attendance_sessions", "semester_id", existing_type=UUID(as_uuid=True), nullable=False)
    op.create_foreign_key(
        "fk_att_sessions_semester", "sis_attendance_sessions",
        "acad_semesters", ["semester_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_att_sessions_semester_date", "sis_attendance_sessions", ["semester_id", "session_date"])

    # 2. A section is now optional.
    op.alter_column("sis_attendance_sessions", "section_id", existing_type=UUID(as_uuid=True), nullable=True)

    # 3. One constraint cannot cover both shapes — NULL section_id defeats it.
    op.drop_constraint(
        "uq_att_sessions_course_section_date_period", "sis_attendance_sessions", type_="unique",
    )
    op.create_index(
        "uq_att_sessions_section_class", "sis_attendance_sessions",
        ["course_id", "section_id", "session_date", "period_number"],
        unique=True, postgresql_where=sa.text("section_id IS NOT NULL"),
    )
    op.create_index(
        "uq_att_sessions_elective_class", "sis_attendance_sessions",
        ["course_id", "semester_id", "session_date", "period_number"],
        unique=True, postgresql_where=sa.text("section_id IS NULL"),
    )


def downgrade() -> None:
    """An elective-group session has no section to restore, so it cannot be
    represented in the old shape. Those rows are deleted — they only exist if
    the tenant ran the new workflow, and there is nowhere to put them."""
    op.execute("DELETE FROM sis_attendance_sessions WHERE section_id IS NULL")

    op.drop_index("uq_att_sessions_elective_class", table_name="sis_attendance_sessions")
    op.drop_index("uq_att_sessions_section_class", table_name="sis_attendance_sessions")
    op.create_unique_constraint(
        "uq_att_sessions_course_section_date_period", "sis_attendance_sessions",
        ["course_id", "section_id", "session_date", "period_number"],
    )

    op.alter_column("sis_attendance_sessions", "section_id", existing_type=UUID(as_uuid=True), nullable=False)

    op.drop_index("ix_att_sessions_semester_date", table_name="sis_attendance_sessions")
    op.drop_constraint("fk_att_sessions_semester", "sis_attendance_sessions", type_="foreignkey")
    op.drop_column("sis_attendance_sessions", "semester_id")
