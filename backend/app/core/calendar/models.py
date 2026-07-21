"""
Academic Calendar — declared events and holidays.

Deadline-type calendar items (assignment due dates, lab deadlines, exam
schedule, research viva) are NOT stored here — they're aggregated at query
time from their owning modules (m04_assignments, m06_labs_evaluator,
m11_sis exam schedule, m07_research_supervision). This table only holds
calendar content that no other module owns: holidays, one-off events,
announcements, and the dated things a department declares rather than
schedules — an internal assessment, a quiz, a project review.

The type vocabulary is deliberately broad (P1.19) so that anything a student
must know the date of has somewhere to live. It is an application-side enum in
a plain VARCHAR with no CHECK constraint, so it grows without a migration.

Visibility answers "whose calendar does this belong on": the whole institution,
a program, a batch, a section — or PERSONAL, which is the student's own note to
themselves, visible only to whoever created it.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class AcademicEventType(str, enum.Enum):
    # Non-teaching days.
    HOLIDAY            = "HOLIDAY"
    GOVERNMENT_HOLIDAY = "GOVERNMENT_HOLIDAY"
    UNIVERSITY_HOLIDAY = "UNIVERSITY_HOLIDAY"
    # Things that happen.
    EVENT              = "EVENT"
    DEPARTMENT_EVENT   = "DEPARTMENT_EVENT"
    ANNOUNCEMENT       = "ANNOUNCEMENT"
    # Dated assessment a department declares rather than schedules through SIS.
    INTERNAL_ASSESSMENT = "INTERNAL_ASSESSMENT"
    QUIZ               = "QUIZ"
    LAB_EXAM           = "LAB_EXAM"
    PROJECT_REVIEW     = "PROJECT_REVIEW"
    RESEARCH_MILESTONE = "RESEARCH_MILESTONE"
    SUBMISSION_DEADLINE = "SUBMISSION_DEADLINE"
    # A student's own note to themselves.
    PERSONAL           = "PERSONAL"
    OTHER              = "OTHER"


class AcademicEventVisibility(str, enum.Enum):
    ALL      = "ALL"
    PROGRAM  = "PROGRAM"
    BATCH    = "BATCH"
    SECTION  = "SECTION"
    # Visible only to whoever created it. This is what makes a student's own
    # academic events private without a second table to hold them.
    PERSONAL = "PERSONAL"


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

    # NULL = seeded reference data with no author. Nobody at the institution
    # decided that Independence Day is the 15th of August; every other event here
    # was somebody's decision and carries them.
    created_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at   = Column(DateTime(timezone=True), nullable=True)
