"""
SIS Examination Management — H59 SQLAlchemy models.

Tables:
  sis_exam_centers      — venue master (internal/external)
  sis_exam_sessions     — one exam event per semester
  sis_exam_schedules    — per-subject timetable within a session
  sis_exam_invigilation — faculty room assignments

Session lifecycle:
  DRAFT → PUBLISHED → SEATING_ALLOCATED → LOCKED → COMPLETED

H58 sis_hall_ticket_eligibility already carries nullable FK placeholders
(exam_session_id, exam_center_id, room_number, seat_number) populated
by the seat-allocation action in ExamService.allocate_seats().
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey,
    Index, Integer, String, Text, Time, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class ExamSessionType(str, enum.Enum):
    REGULAR       = "REGULAR"
    SUPPLEMENTARY = "SUPPLEMENTARY"
    REVALUATION   = "REVALUATION"
    IMPROVEMENT   = "IMPROVEMENT"


class ExamSessionStatus(str, enum.Enum):
    DRAFT             = "DRAFT"
    PUBLISHED         = "PUBLISHED"
    SEATING_ALLOCATED = "SEATING_ALLOCATED"
    LOCKED            = "LOCKED"
    COMPLETED         = "COMPLETED"


class SisExamCenter(Base):
    __tablename__ = "sis_exam_centers"
    __table_args__ = (
        UniqueConstraint("center_code", name="uq_exam_centers_code"),
        Index("ix_exam_centers_is_active",   "is_active"),
        Index("ix_exam_centers_is_internal", "is_internal"),
    )

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    center_code = Column(String(20),  nullable=False)
    center_name = Column(String(200), nullable=False)
    address     = Column(Text,        nullable=True)
    capacity    = Column(Integer,     nullable=True)
    is_internal = Column(Boolean,     nullable=False, server_default=text("true"))
    is_active   = Column(Boolean,     nullable=False, server_default=text("true"))
    created_at  = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at  = Column(DateTime(timezone=True), nullable=True)


class SisExamSession(Base):
    __tablename__ = "sis_exam_sessions"
    __table_args__ = (
        Index("ix_exam_sessions_semester_id",   "semester_id"),
        Index("ix_exam_sessions_status",        "status"),
        Index("ix_exam_sessions_session_type",  "session_type"),
        Index("ix_exam_sessions_semester_type", "semester_id", "session_type"),
    )

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    semester_id  = Column(UUID(as_uuid=True),
                          ForeignKey("acad_semesters.id", ondelete="RESTRICT"), nullable=False)
    session_type = Column(String(20),  nullable=False)
    session_name = Column(String(100), nullable=False)
    academic_year = Column(String(20), nullable=False)
    start_date   = Column(Date,        nullable=False)
    end_date     = Column(Date,        nullable=False)
    status       = Column(String(20),  nullable=False, server_default=text("'DRAFT'"))
    notes        = Column(Text,        nullable=True)

    # Future-proof linkage to parent session (e.g. SUPPLEMENTARY → REGULAR)
    source_exam_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sis_exam_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    attempt_number = Column(Integer, nullable=True)

    # Hall ticket readiness tracking
    hall_ticket_generated_at = Column(DateTime(timezone=True), nullable=True)
    hall_ticket_generated_by = Column(UUID(as_uuid=True),      nullable=True)

    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=True)


class SisExamSchedule(Base):
    __tablename__ = "sis_exam_schedules"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "course_id", "section_id",
            name="uq_exam_schedule_session_course_section",
        ),
        Index("ix_exam_schedules_session_id", "session_id"),
        Index("ix_exam_schedules_course_id",  "course_id"),
        Index("ix_exam_schedules_section_id", "section_id"),
        Index("ix_exam_schedules_exam_date",  "exam_date"),
    )

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id  = Column(UUID(as_uuid=True),
                         ForeignKey("sis_exam_sessions.id",  ondelete="RESTRICT"), nullable=False)
    course_id   = Column(UUID(as_uuid=True),
                         ForeignKey("courses.id",            ondelete="RESTRICT"), nullable=False)
    section_id  = Column(UUID(as_uuid=True),
                         ForeignKey("acad_sections.id",      ondelete="RESTRICT"), nullable=False)
    center_id   = Column(UUID(as_uuid=True),
                         ForeignKey("sis_exam_centers.id",   ondelete="SET NULL"),  nullable=True)
    exam_date   = Column(Date,        nullable=False)
    start_time  = Column(Time,        nullable=False)
    end_time    = Column(Time,        nullable=False)
    room_number = Column(String(30),  nullable=True)
    notes       = Column(Text,        nullable=True)
    created_by  = Column(UUID(as_uuid=True), nullable=False)
    created_at  = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at  = Column(DateTime(timezone=True), nullable=True)


class SisExamInvigilation(Base):
    __tablename__ = "sis_exam_invigilation"
    __table_args__ = (
        Index("ix_exam_invigilation_session_id",      "session_id"),
        Index("ix_exam_invigilation_faculty_user_id", "faculty_user_id"),
        Index("ix_exam_invigilation_schedule_id",     "schedule_id"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id      = Column(UUID(as_uuid=True),
                             ForeignKey("sis_exam_sessions.id",  ondelete="RESTRICT"), nullable=False)
    schedule_id     = Column(UUID(as_uuid=True),
                             ForeignKey("sis_exam_schedules.id", ondelete="SET NULL"),  nullable=True)
    center_id       = Column(UUID(as_uuid=True),
                             ForeignKey("sis_exam_centers.id",   ondelete="SET NULL"),  nullable=True)
    room_number     = Column(String(30), nullable=True)
    faculty_user_id = Column(UUID(as_uuid=True), nullable=False)  # plain UUID
    assigned_by     = Column(UUID(as_uuid=True), nullable=False)  # plain UUID
    notes           = Column(Text,        nullable=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
