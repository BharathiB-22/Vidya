"""
Class Timetable — recurring weekly schedule per section+semester.

Workflow: Admin creates a DRAFT timetable and adds slots -> submits for
review (PENDING_REVIEW) -> Dean approves (APPROVED) or rejects (REJECTED,
back to editable) -> Admin publishes (PUBLISHED) -> visible to students
(their section) and faculty (their own slots across all sections).

Distinct from the per-session EXAM timetable in m11_sis (sis_exam_schedules)
- this is the recurring weekly lecture/lab schedule, not exam scheduling.
Room/faculty double-booking across different timetables is not validated in
this pass (each timetable is scoped to one section+semester; cross-section
faculty/room conflicts are a Phase 5 concern).
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, Time,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base


class TimetableStatus(str, enum.Enum):
    DRAFT           = "DRAFT"
    PENDING_REVIEW  = "PENDING_REVIEW"
    APPROVED        = "APPROVED"
    REJECTED        = "REJECTED"
    PUBLISHED       = "PUBLISHED"


class SaturdayMode(str, enum.Enum):
    FULL    = "FULL"
    HALF    = "HALF"
    HOLIDAY = "HOLIDAY"


class PeriodType(str, enum.Enum):
    PERIOD = "PERIOD"
    BREAK  = "BREAK"


class Timetable(Base):
    __tablename__ = "timetables"
    __table_args__ = (
        UniqueConstraint("section_id", "semester_id", name="uq_timetables_section_semester"),
        Index("ix_timetables_section_id", "section_id"),
        Index("ix_timetables_semester_id", "semester_id"),
        Index("ix_timetables_status", "status"),
    )

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id  = Column(UUID(as_uuid=True), ForeignKey("acad_sections.id", ondelete="CASCADE"), nullable=False)
    semester_id = Column(UUID(as_uuid=True), ForeignKey("acad_semesters.id", ondelete="CASCADE"), nullable=False)
    # Optional link to the department's schedule template (working days,
    # periods, breaks). Nullable so pre-existing timetables (created before
    # Phase 4.1) keep working with plain period numbers, no real times.
    template_id = Column(UUID(as_uuid=True), ForeignKey("timetable_templates.id", ondelete="SET NULL"), nullable=True)

    status = Column(String(20), nullable=False, default=TimetableStatus.DRAFT.value)

    created_by_user_id  = Column(UUID(as_uuid=True), nullable=False)
    submitted_at        = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    reviewed_at         = Column(DateTime(timezone=True), nullable=True)
    review_comment      = Column(Text, nullable=True)
    published_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    published_at        = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=True)


class TimetableSlot(Base):
    __tablename__ = "timetable_slots"
    __table_args__ = (
        UniqueConstraint("timetable_id", "day_of_week", "period_number", name="uq_timetable_slot_period"),
        Index("ix_timetable_slots_timetable_id", "timetable_id"),
        Index("ix_timetable_slots_course_id", "course_id"),
        Index("ix_timetable_slots_faculty_user_id", "faculty_user_id"),
    )

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timetable_id = Column(UUID(as_uuid=True), ForeignKey("timetables.id", ondelete="CASCADE"), nullable=False)

    day_of_week    = Column(Integer, nullable=False)  # 0=Monday .. 6=Sunday
    period_number  = Column(Integer, nullable=False)  # 1..8
    course_id      = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    faculty_user_id = Column(UUID(as_uuid=True), nullable=True)
    room           = Column(String(50), nullable=True)
    # Optional free-text note for this slot (e.g. "Tutorial", "Guest lecture").
    remarks        = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


# ---------------------------------------------------------------------------
# TimetableTemplate / TimetablePeriod (Phase 4.1) — department-owned schedule
# shape (working days, Saturday mode, college hours) plus its ordered
# period/break sequence. A Timetable optionally links to one template so its
# grid can render real clock times and break rows instead of bare period
# numbers. Department isolation for these belongs to the Dean who governs
# that department (see core/timetable/dean_scope.py).
# ---------------------------------------------------------------------------

class TimetableTemplate(Base):
    __tablename__ = "timetable_templates"
    __table_args__ = (
        Index("ix_timetable_templates_department_id", "department_id"),
    )

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    department_id  = Column(UUID(as_uuid=True), ForeignKey("acad_departments.id", ondelete="CASCADE"), nullable=False)
    name           = Column(String, nullable=False)
    # e.g. [0,1,2,3,4] Mon-Fri, [0,1,2,3,4,5] Mon-Sat (0=Monday..6=Sunday)
    working_days   = Column(JSONB, nullable=False)
    # FULL | HALF | HOLIDAY — only meaningful when 5 (Saturday) is in working_days;
    # HOLIDAY implies Saturday is simply absent from working_days.
    saturday_mode  = Column(String(10), nullable=True)
    college_start_time = Column(Time, nullable=False)
    college_end_time   = Column(Time, nullable=False)

    created_by_user_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=True)


class TimetablePeriod(Base):
    __tablename__ = "timetable_periods"
    __table_args__ = (
        UniqueConstraint("template_id", "sequence_number", name="uq_timetable_period_sequence"),
        Index("ix_timetable_periods_template_id", "template_id"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id     = Column(UUID(as_uuid=True), ForeignKey("timetable_templates.id", ondelete="CASCADE"), nullable=False)
    sequence_number = Column(Integer, nullable=False)  # display order, includes breaks
    period_type     = Column(String(10), nullable=False)  # PERIOD | BREAK
    # Set only when period_type == PERIOD; this is what TimetableSlot.period_number
    # references. Null for BREAK rows (a partial unique index enforces
    # uniqueness among non-null values per template — see migration).
    period_number   = Column(Integer, nullable=True)
    # BREAK: "Tea Break" / "Lunch Break" / "Prayer Break" / "Department Meeting" /
    # custom text. PERIOD: optional label override (else frontend shows "Period N").
    label           = Column(String(50), nullable=True)
    start_time      = Column(Time, nullable=False)
    end_time        = Column(Time, nullable=False)
    # If the template's saturday_mode == HALF, periods marked True don't apply
    # on the Saturday column (afternoon periods typically).
    skip_on_half_day = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
