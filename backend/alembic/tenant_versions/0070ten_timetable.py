"""tenant: create timetables & timetable_slots tables (class timetable)

Revision ID: 0070ten
Revises: 0069ten
Create Date: 2026-07-06

Tables created (tenant schema):
  timetables       — one row per section+semester; DRAFT -> PENDING_REVIEW ->
                      APPROVED -> PUBLISHED (or REJECTED back to editable).
  timetable_slots  — recurring weekly slots (day_of_week, period_number,
                      course, faculty, room) belonging to one timetable.

Distinct from the per-session EXAM timetable in m11_sis (sis_exam_schedules)
- this is the recurring weekly class/lecture schedule.

NOTE: current tip was 0069ten at the time this migration was authored. A
parallel Electives-workflow migration may also be landing this round — if
both picked the same next number, the coordinator must renumber one of them
to keep the chain linear before this is applied.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0070ten"
down_revision = "0069ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "timetables",
        sa.Column("id",                    postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("section_id",            postgresql.UUID(as_uuid=True), sa.ForeignKey("acad_sections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("semester_id",           postgresql.UUID(as_uuid=True), sa.ForeignKey("acad_semesters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status",                sa.String(20),                 nullable=False, server_default="DRAFT"),
        sa.Column("created_by_user_id",    postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_at",          sa.DateTime(timezone=True),    nullable=True),
        sa.Column("reviewed_by_user_id",   postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at",           sa.DateTime(timezone=True),    nullable=True),
        sa.Column("review_comment",        sa.Text(),                     nullable=True),
        sa.Column("published_by_user_id",  postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_at",          sa.DateTime(timezone=True),    nullable=True),
        sa.Column("created_at",            sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",            sa.DateTime(timezone=True),    nullable=True),
        sa.UniqueConstraint("section_id", "semester_id", name="uq_timetables_section_semester"),
    )
    op.create_index("ix_timetables_section_id",  "timetables", ["section_id"])
    op.create_index("ix_timetables_semester_id", "timetables", ["semester_id"])
    op.create_index("ix_timetables_status",      "timetables", ["status"])

    op.create_table(
        "timetable_slots",
        sa.Column("id",               postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("timetable_id",     postgresql.UUID(as_uuid=True), sa.ForeignKey("timetables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day_of_week",      sa.Integer(),                  nullable=False),
        sa.Column("period_number",    sa.Integer(),                  nullable=False),
        sa.Column("course_id",        postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("faculty_user_id",  postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("room",             sa.String(50),                 nullable=True),
        sa.Column("created_at",       sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("timetable_id", "day_of_week", "period_number", name="uq_timetable_slot_period"),
    )
    op.create_index("ix_timetable_slots_timetable_id",     "timetable_slots", ["timetable_id"])
    op.create_index("ix_timetable_slots_course_id",        "timetable_slots", ["course_id"])
    op.create_index("ix_timetable_slots_faculty_user_id",  "timetable_slots", ["faculty_user_id"])


def downgrade() -> None:
    op.drop_index("ix_timetable_slots_faculty_user_id", table_name="timetable_slots")
    op.drop_index("ix_timetable_slots_course_id",        table_name="timetable_slots")
    op.drop_index("ix_timetable_slots_timetable_id",     table_name="timetable_slots")
    op.drop_table("timetable_slots")

    op.drop_index("ix_timetables_status",      table_name="timetables")
    op.drop_index("ix_timetables_semester_id", table_name="timetables")
    op.drop_index("ix_timetables_section_id",  table_name="timetables")
    op.drop_table("timetables")
