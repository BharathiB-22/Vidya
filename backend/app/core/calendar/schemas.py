from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.calendar.models import AcademicEventType, AcademicEventVisibility


class CalendarItem(BaseModel):
    """Normalized shape for every calendar entry, regardless of source module.

    Every dated academic thing a student must know about arrives here in the same
    shape, so the calendar never has to know which module owns what.
    """
    id: str
    title: str
    # One line of context — the course code, the room, the exam session. Whatever
    # makes the title mean something without opening it.
    detail: str | None = None
    # An AcademicEventType, or one of the aggregated deadline kinds:
    # ASSIGNMENT_DUE | LAB_DUE | EXAM | VIVA.
    item_type: str
    date: date
    start_time: time | None = None
    end_time: time | None = None
    all_day: bool = False
    source_module: str  # calendar | assignments | labs | exam | research
    link: str | None = None
    # True only for the student's own PERSONAL notes — the only items on this
    # calendar that are theirs to remove.
    editable: bool = False


class AcademicEventCreate(BaseModel):
    title: str
    description: str | None = None
    event_type: AcademicEventType = AcademicEventType.EVENT
    start_at: datetime
    end_at: datetime | None = None
    is_all_day: bool = False
    visibility: AcademicEventVisibility = AcademicEventVisibility.ALL
    program_id: UUID | None = None
    batch_id: UUID | None = None
    section_id: UUID | None = None


class AcademicEventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    event_type: AcademicEventType | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    is_all_day: bool | None = None
    visibility: AcademicEventVisibility | None = None
    program_id: UUID | None = None
    batch_id: UUID | None = None
    section_id: UUID | None = None


class AcademicEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    event_type: str
    start_at: datetime
    end_at: datetime | None
    is_all_day: bool
    visibility: str
    program_id: UUID | None
    batch_id: UUID | None
    section_id: UUID | None
    # NULL for seeded reference data (the fixed-date national holidays), which
    # nobody authored.
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime | None


class TeachingDays(BaseModel):
    """Which weekdays this student actually has class on, 0=Monday .. 6=Sunday.

    Read off their section's PUBLISHED timetable, because "is Saturday a holiday"
    has no general answer — some institutions teach on Saturday, some teach on
    alternate Saturdays, and some do not teach at all. The calendar greys a day
    out only when the student's own timetable is silent on it, so a student with
    Saturday classes never sees Saturday marked as a non-teaching day.
    """
    teaching_days: list[int]
