from __future__ import annotations

from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TimetableSlotCreate(BaseModel):
    day_of_week: int      # 0=Monday..6=Sunday
    period_number: int
    course_id: UUID
    faculty_user_id: UUID | None = None
    room: str | None = None
    remarks: str | None = None


class TimetableSlotUpdate(BaseModel):
    """Move a slot (day_of_week / period_number) or edit it in place.

    Every field is optional; only what is sent changes. The service validates the
    slot's *resulting* position, so a rejected move leaves it where it was.
    """
    day_of_week: int | None = None
    period_number: int | None = None
    faculty_user_id: UUID | None = None
    room: str | None = None
    remarks: str | None = None


class TimetableSlotSwap(BaseModel):
    """Exchange the day/period of two slots in the same timetable."""
    slot_a_id: UUID
    slot_b_id: UUID


class TimetableSlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    day_of_week: int
    period_number: int
    course_id: UUID
    course_code: str | None = None
    course_title: str | None = None
    faculty_user_id: UUID | None = None
    faculty_name: str | None = None
    room: str | None = None
    remarks: str | None = None
    # True when the course is an elective choice. Read-only, and purely so the
    # grid can badge the cell as a combined class: an elective is taught to every
    # student who chose it, across sections, not to the one section this
    # timetable belongs to. Scheduling that combined class is a later phase.
    is_elective: bool = False
    # Resolved from the timetable's linked template's matching period, when
    # one exists — null otherwise (pre-Phase-4.1 timetables with no template).
    start_time: time | None = None
    end_time: time | None = None
    period_label: str | None = None


class TimetableCreate(BaseModel):
    section_id: UUID
    semester_id: UUID
    template_id: UUID | None = None


class TimetableUpdate(BaseModel):
    """Re-point a draft timetable at a different schedule template.

    Sending `template_id: null` detaches the template and falls back to bare
    Period 1..8. Refused if any existing slot sits on a period the new template
    does not teach — those entries would silently disappear from the grid.
    """
    template_id: UUID | None = None


class TimetableRejectRequest(BaseModel):
    comment: str


# ---------------------------------------------------------------------------
# Timetable Template / Period (Phase 4.1)
# ---------------------------------------------------------------------------

class TimetablePeriodCreate(BaseModel):
    sequence_number: int
    period_type: str          # PERIOD | BREAK
    period_number: int | None = None   # required iff period_type == PERIOD
    label: str | None = None
    start_time: time
    end_time: time
    skip_on_half_day: bool = False


class TimetablePeriodUpdate(BaseModel):
    sequence_number: int | None = None
    period_type: str | None = None
    period_number: int | None = None
    label: str | None = None
    start_time: time | None = None
    end_time: time | None = None
    skip_on_half_day: bool | None = None


class TimetablePeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sequence_number: int
    period_type: str
    period_number: int | None = None
    label: str | None = None
    start_time: time
    end_time: time
    skip_on_half_day: bool


class TimetableTemplateCreate(BaseModel):
    department_id: UUID
    name: str
    working_days: list[int]
    saturday_mode: str | None = None   # FULL | HALF | HOLIDAY
    college_start_time: time
    college_end_time: time


class TimetableTemplateUpdate(BaseModel):
    name: str | None = None
    working_days: list[int] | None = None
    saturday_mode: str | None = None
    college_start_time: time | None = None
    college_end_time: time | None = None


class TimetableTemplateOut(BaseModel):
    id: UUID
    department_id: UUID
    department_name: str | None = None
    name: str
    working_days: list[int]
    saturday_mode: str | None = None
    college_start_time: time
    college_end_time: time
    periods: list[TimetablePeriodOut] = []
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime | None = None


class TimetableTemplateListItem(BaseModel):
    id: UUID
    department_id: UUID
    department_name: str | None = None
    name: str
    working_days: list[int]
    saturday_mode: str | None = None
    college_start_time: time
    college_end_time: time
    period_count: int = 0
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Timetable (extended with optional template link/embed)
# ---------------------------------------------------------------------------

class TimetableOut(BaseModel):
    id: UUID
    section_id: UUID
    section_name: str | None = None
    semester_id: UUID
    semester_label: str | None = None
    program_name: str | None = None
    # Code + batch years are what tell two live admissions of the same programme
    # apart — "MCA (2026–2028)" vs "MCA (2025–2027)".
    program_code: str | None = None
    academic_year: str | None = None
    status: str
    slots: list[TimetableSlotOut] = []
    template_id: UUID | None = None
    template: TimetableTemplateOut | None = None
    created_by_user_id: UUID
    submitted_at: datetime | None = None
    reviewed_by_user_id: UUID | None = None
    reviewed_at: datetime | None = None
    review_comment: str | None = None
    published_by_user_id: UUID | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class TimetableListItem(BaseModel):
    id: UUID
    section_id: UUID
    section_name: str | None = None
    semester_id: UUID
    semester_label: str | None = None
    program_name: str | None = None
    program_code: str | None = None
    academic_year: str | None = None
    status: str
    slot_count: int = 0
    template_id: UUID | None = None
    created_by_user_id: UUID
    submitted_at: datetime | None = None
    published_at: datetime | None = None
    created_at: datetime


class StudentTimetableOut(BaseModel):
    section_id: UUID
    section_name: str | None = None
    semester_label: str | None = None
    program_name: str | None = None
    academic_year: str | None = None
    slots: list[TimetableSlotOut] = []
    template: TimetableTemplateOut | None = None


class FacultyTimetableSlotOut(TimetableSlotOut):
    section_name: str | None = None
    semester_name: str | None = None
    program_name: str | None = None


class FacultyTimetableOut(BaseModel):
    slots: list[FacultyTimetableSlotOut] = []
