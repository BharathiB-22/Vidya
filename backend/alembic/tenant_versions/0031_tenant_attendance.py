"""0031 – SIS H55: create sis_attendance_sessions and sis_attendance_records

Two new tables for classroom attendance tracking.

Business rules baked into schema:
  - session UNIQUE on (course_id, section_id, session_date, period_number) for non-NULL period
  - partial UNIQUE index for sessions with no period_number (NULL period per course+section+date)
  - records UNIQUE on (session_id, student_id)
  - first_marked_at on sessions tracks start of 48-hour edit window (per policy: window
    runs from first save, not session creation)
  - edit tracking: marked_by/marked_at for first save; edited_by/edited_at/edit_reason for
    subsequent edits (edit_reason mandatory per H55 policy decision)
  - reopened_by/reopened_at/reopen_reason support ADMIN/DEAN reopen workflow

No changes to existing tables.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision      = "0031ten"
down_revision = "0030ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Table 1: sis_attendance_sessions
    # ------------------------------------------------------------------
    op.create_table(
        "sis_attendance_sessions",
        sa.Column("id",               UUID(as_uuid=True), primary_key=True),

        # Context
        sa.Column("course_id",        UUID(as_uuid=True),
                  sa.ForeignKey("courses.id",         ondelete="CASCADE"), nullable=False),
        sa.Column("section_id",       UUID(as_uuid=True),
                  sa.ForeignKey("acad_sections.id",   ondelete="CASCADE"), nullable=False),
        sa.Column("faculty_user_id",  UUID(as_uuid=True), nullable=False),   # plain UUID (codebase pattern)

        # When
        sa.Column("session_date",     sa.Date,        nullable=False),
        sa.Column("period_number",    sa.SmallInteger, nullable=True),
        sa.Column("duration_minutes", sa.SmallInteger, nullable=True),

        # Content
        sa.Column("topic_covered",    sa.Text,        nullable=True),

        # Lifecycle
        sa.Column("status",           sa.String(10),  nullable=False, server_default="OPEN"),
        sa.Column("first_marked_at",  sa.DateTime(timezone=True), nullable=True),   # 48h window anchor
        sa.Column("locked_at",        sa.DateTime(timezone=True), nullable=True),

        # Reopen
        sa.Column("reopened_by",      UUID(as_uuid=True), nullable=True),
        sa.Column("reopened_at",      sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopen_reason",    sa.Text,        nullable=True),

        # Standard audit
        sa.Column("created_at",       sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",       sa.DateTime(timezone=True), nullable=True),
    )

    # UNIQUE: non-NULL period (two periods in same slot is a conflict)
    op.create_unique_constraint(
        "uq_att_sessions_course_section_date_period",
        "sis_attendance_sessions",
        ["course_id", "section_id", "session_date", "period_number"],
    )

    # Partial UNIQUE: only one period-less session per course+section+date
    op.execute("""
        CREATE UNIQUE INDEX uq_att_sessions_no_period
        ON sis_attendance_sessions (course_id, section_id, session_date)
        WHERE period_number IS NULL
    """)

    # Indexes
    op.create_index("ix_att_sessions_section_date",  "sis_attendance_sessions", ["section_id",      "session_date"])
    op.create_index("ix_att_sessions_course_date",   "sis_attendance_sessions", ["course_id",       "session_date"])
    op.create_index("ix_att_sessions_faculty_date",  "sis_attendance_sessions", ["faculty_user_id", "session_date"])
    op.create_index("ix_att_sessions_status",        "sis_attendance_sessions", ["status"])
    op.create_index("ix_att_sessions_date",          "sis_attendance_sessions", ["session_date"])
    op.create_index("ix_att_sessions_first_marked",  "sis_attendance_sessions", ["first_marked_at"])

    # ------------------------------------------------------------------
    # Table 2: sis_attendance_records
    # ------------------------------------------------------------------
    op.create_table(
        "sis_attendance_records",
        sa.Column("id",          UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id",  UUID(as_uuid=True),
                  sa.ForeignKey("sis_attendance_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id",  UUID(as_uuid=True), nullable=False),   # plain UUID (codebase pattern)

        # Attendance value
        sa.Column("status",   sa.String(10), nullable=False, server_default="ABSENT"),
        sa.Column("remarks",  sa.Text,       nullable=True),

        # First mark (set when faculty first saves attendance for this record)
        sa.Column("marked_by",  UUID(as_uuid=True),           nullable=True),
        sa.Column("marked_at",  sa.DateTime(timezone=True),   nullable=True),

        # Edit tracking (populated only on subsequent edits)
        sa.Column("edited_by",    UUID(as_uuid=True),          nullable=True),
        sa.Column("edited_at",    sa.DateTime(timezone=True),  nullable=True),
        sa.Column("edit_reason",  sa.Text,                     nullable=True),
    )

    op.create_unique_constraint(
        "uq_att_records_session_student",
        "sis_attendance_records",
        ["session_id", "student_id"],
    )

    op.create_index("ix_att_records_session",        "sis_attendance_records", ["session_id"])
    op.create_index("ix_att_records_student",        "sis_attendance_records", ["student_id"])
    op.create_index("ix_att_records_student_status", "sis_attendance_records", ["student_id", "status"])


def downgrade() -> None:
    # Records first (FK on session_id)
    op.drop_index("ix_att_records_student_status", table_name="sis_attendance_records")
    op.drop_index("ix_att_records_student",        table_name="sis_attendance_records")
    op.drop_index("ix_att_records_session",        table_name="sis_attendance_records")
    op.drop_constraint("uq_att_records_session_student", "sis_attendance_records", type_="unique")
    op.drop_table("sis_attendance_records")

    # Sessions
    op.drop_index("ix_att_sessions_first_marked",  table_name="sis_attendance_sessions")
    op.drop_index("ix_att_sessions_date",          table_name="sis_attendance_sessions")
    op.drop_index("ix_att_sessions_status",        table_name="sis_attendance_sessions")
    op.drop_index("ix_att_sessions_faculty_date",  table_name="sis_attendance_sessions")
    op.drop_index("ix_att_sessions_course_date",   table_name="sis_attendance_sessions")
    op.drop_index("ix_att_sessions_section_date",  table_name="sis_attendance_sessions")
    op.execute("DROP INDEX IF EXISTS uq_att_sessions_no_period")
    op.drop_constraint("uq_att_sessions_course_section_date_period", "sis_attendance_sessions", type_="unique")
    op.drop_table("sis_attendance_sessions")
