"""0034 – H59: Examination Management

New tables:
  sis_exam_centers      — venue master (MAIN center seeded automatically)
  sis_exam_sessions     — exam event per semester (REGULAR / SUPPLEMENTARY / etc.)
  sis_exam_schedules    — per-subject timetable within a session
  sis_exam_invigilation — faculty room assignments

Session lifecycle:
  DRAFT → PUBLISHED → SEATING_ALLOCATED → LOCKED → COMPLETED

H58 sis_hall_ticket_eligibility already carries the nullable placeholders
(exam_session_id, exam_center_id, room_number, seat_number) that are
populated by the seat-allocation step defined in this module.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision     = "0034ten"
down_revision = "0033ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── sis_exam_centers (created first; referenced by sessions and schedules) ──
    op.create_table(
        "sis_exam_centers",
        sa.Column("id",          postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("center_code", sa.String(20),  nullable=False),
        sa.Column("center_name", sa.String(200), nullable=False),
        sa.Column("address",     sa.Text,         nullable=True),
        sa.Column("capacity",    sa.Integer,      nullable=True),
        sa.Column("is_internal", sa.Boolean,      nullable=False, server_default=sa.text("true")),
        sa.Column("is_active",   sa.Boolean,      nullable=False, server_default=sa.text("true")),
        sa.Column("created_at",  sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",  sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("center_code", name="uq_exam_centers_code"),
    )
    op.create_index("ix_exam_centers_is_active",   "sis_exam_centers", ["is_active"])
    op.create_index("ix_exam_centers_is_internal", "sis_exam_centers", ["is_internal"])

    # ── sis_exam_sessions ────────────────────────────────────────────────────
    op.create_table(
        "sis_exam_sessions",
        sa.Column("id",           postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("semester_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_type", sa.String(20),  nullable=False),
        sa.Column("session_name", sa.String(100), nullable=False),
        sa.Column("academic_year",sa.String(20),  nullable=False),
        sa.Column("start_date",   sa.Date,         nullable=False),
        sa.Column("end_date",     sa.Date,         nullable=False),
        sa.Column("status",       sa.String(20),   nullable=False,
                  server_default=sa.text("'DRAFT'")),
        sa.Column("notes",        sa.Text,          nullable=True),
        # Future-proof: link to original session for SUPPLEMENTARY / REVALUATION
        sa.Column("source_exam_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Attempt number for REVALUATION / IMPROVEMENT
        sa.Column("attempt_number", sa.Integer, nullable=True),
        # Hall ticket readiness tracking
        sa.Column("hall_ticket_generated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("hall_ticket_generated_by", postgresql.UUID(as_uuid=True), nullable=True),
        # Audit
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["semester_id"], ["acad_semesters.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_exam_session_id"], ["sis_exam_sessions.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_exam_sessions_semester_id",  "sis_exam_sessions", ["semester_id"])
    op.create_index("ix_exam_sessions_status",       "sis_exam_sessions", ["status"])
    op.create_index("ix_exam_sessions_session_type", "sis_exam_sessions", ["session_type"])
    op.create_index("ix_exam_sessions_semester_type",
                    "sis_exam_sessions", ["semester_id", "session_type"])

    # ── sis_exam_schedules ───────────────────────────────────────────────────
    op.create_table(
        "sis_exam_schedules",
        sa.Column("id",          postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id",   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("center_id",   postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("exam_date",   sa.Date,    nullable=False),
        sa.Column("start_time",  sa.Time,    nullable=False),
        sa.Column("end_time",    sa.Time,    nullable=False),
        sa.Column("room_number", sa.String(30), nullable=True),
        sa.Column("notes",       sa.Text,     nullable=True),
        sa.Column("created_by",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at",  sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",  sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["sis_exam_sessions.id"],  ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["course_id"],  ["courses.id"],            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["section_id"], ["acad_sections.id"],      ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["center_id"],  ["sis_exam_centers.id"],   ondelete="SET NULL"),
        sa.UniqueConstraint(
            "session_id", "course_id", "section_id",
            name="uq_exam_schedule_session_course_section",
        ),
    )
    op.create_index("ix_exam_schedules_session_id",  "sis_exam_schedules", ["session_id"])
    op.create_index("ix_exam_schedules_course_id",   "sis_exam_schedules", ["course_id"])
    op.create_index("ix_exam_schedules_section_id",  "sis_exam_schedules", ["section_id"])
    op.create_index("ix_exam_schedules_exam_date",   "sis_exam_schedules", ["exam_date"])

    # ── sis_exam_invigilation ────────────────────────────────────────────────
    op.create_table(
        "sis_exam_invigilation",
        sa.Column("id",              postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id",      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_id",     postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("center_id",       postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("room_number",     sa.String(30), nullable=True),
        sa.Column("faculty_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_by",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notes",           sa.Text,        nullable=True),
        sa.Column("created_at",      sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"],  ["sis_exam_sessions.id"],  ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["schedule_id"], ["sis_exam_schedules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["center_id"],   ["sis_exam_centers.id"],   ondelete="SET NULL"),
    )
    op.create_index("ix_exam_invigilation_session_id",
                    "sis_exam_invigilation", ["session_id"])
    op.create_index("ix_exam_invigilation_faculty_user_id",
                    "sis_exam_invigilation", ["faculty_user_id"])
    op.create_index("ix_exam_invigilation_schedule_id",
                    "sis_exam_invigilation", ["schedule_id"])

    # ── Seed default exam center ─────────────────────────────────────────────
    op.execute(
        """
        INSERT INTO sis_exam_centers
            (id, center_code, center_name, is_internal, is_active, created_at)
        VALUES
            (gen_random_uuid(), 'MAIN', 'Main Campus', true, true, now())
        ON CONFLICT (center_code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("sis_exam_invigilation")
    op.drop_table("sis_exam_schedules")
    op.drop_table("sis_exam_sessions")
    op.drop_table("sis_exam_centers")
