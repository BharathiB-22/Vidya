"""
Academic Calendar — admin/dean-declared events and holidays.

Deadline-type calendar items (assignment due dates, lab deadlines, exam
schedule, research viva) are NOT stored here — they're aggregated at query
time from their owning modules (m04_assignments, m06_labs_evaluator,
m11_sis exam schedule, m07_research_supervision). This table only holds
genuinely new calendar content: holidays, one-off events, announcements.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class AcademicEventType(str, enum.Enum):
    HOLIDAY      = "HOLIDAY"
    EVENT        = "EVENT"
    ANNOUNCEMENT = "ANNOUNCEMENT"
    OTHER        = "OTHER"


class AcademicEventVisibility(str, enum.Enum):
    ALL     = "ALL"
    PROGRAM = "PROGRAM"
    BATCH   = "BATCH"
    SECTION = "SECTION"


class AcademicEvent(Base):
    __tablename__ = "academic_events"
    __table_args__ = (
        Index("ix_academic_events_start_at", "start_at"),
        Index("ix_academic_events_visibility", "visibility"),
        Index("ix_academic_events_program_id", "program_id"),
        Index("ix_academic_events_batch_id", "batch_id"),
        Index("ix_academic_events_section_id", "section_id"),
    )

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title        = Column(String, nullable=False)
    description  = Column(Text, nullable=True)
    event_type   = Column(String(20), nullable=False, default=AcademicEventType.EVENT.value)
    start_at     = Column(DateTime(timezone=True), nullable=False)
    end_at       = Column(DateTime(timezone=True), nullable=True)
    is_all_day   = Column(Boolean, nullable=False, default=False)

    visibility   = Column(String(10), nullable=False, default=AcademicEventVisibility.ALL.value)
    program_id   = Column(UUID(as_uuid=True), nullable=True)
    batch_id     = Column(UUID(as_uuid=True), nullable=True)
    section_id   = Column(UUID(as_uuid=True), nullable=True)

    created_by_user_id = Column(UUID(as_uuid=True), nullable=False)
    created_at   = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at   = Column(DateTime(timezone=True), nullable=True)
