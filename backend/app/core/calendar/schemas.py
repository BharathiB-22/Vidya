from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.calendar.models import AcademicEventType, AcademicEventVisibility


class CalendarItem(BaseModel):
    """Normalized shape for every calendar entry, regardless of source module."""
    id: str
    title: str
    item_type: str  # HOLIDAY | EVENT | ANNOUNCEMENT | ASSIGNMENT_DUE | LAB_DUE | EXAM | VIVA
    date: date
    start_time: time | None = None
    end_time: time | None = None
    all_day: bool = False
    source_module: str  # calendar | assignments | labs | exam | research
    link: str | None = None


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
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime | None
