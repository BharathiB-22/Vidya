"""
SIS Attendance — H55 SQLAlchemy models.

Tables:
  sis_attendance_sessions  — one row per class period
  sis_attendance_records   — one row per student per session

Session lifecycle:
  OPEN   → editable for 48 hours from first_marked_at (policy: window starts on first save)
  LOCKED → no faculty edits; ADMIN/DEAN may reopen

Record status semantics (Phase 1 MVP — Present/Absent only):
  PRESENT → attended; counted in numerator and denominator
  ABSENT  → not attended; counted in denominator only

Attendance % = PRESENT / (PRESENT + ABSENT) × 100
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Column, Date, DateTime, ForeignKey, Index,
    SmallInteger, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class SessionStatus(str, enum.Enum):
    OPEN   = "OPEN"
    LOCKED = "LOCKED"


class AttendanceStatus(str, enum.Enum):
    PRESENT = "PRESENT"
    ABSENT  = "ABSENT"


class SisAttendanceSession(Base):
    """One class period.

    The class is either a section or an elective group, never both:

      section_id IS NOT NULL   a regular course taught to one section
      section_id IS NULL       an elective group — every student in `semester_id`
                               who registered for `course_id`, across all sections

    Uniqueness is therefore enforced by two partial indexes rather than one
    constraint (see tenant migration 0080ten): a plain UNIQUE over section_id
    would not constrain elective sessions at all, because Postgres treats every
    NULL as distinct.
    """
    __tablename__ = "sis_attendance_sessions"
    __table_args__ = (
        # Regular class: one session per course+section+date+period.
        Index(
            "uq_att_sessions_section_class",
            "course_id", "section_id", "session_date", "period_number",
            unique=True, postgresql_where=text("section_id IS NOT NULL"),
        ),
        # Elective group: one session per course+semester+date+period.
        Index(
            "uq_att_sessions_elective_class",
            "course_id", "semester_id", "session_date", "period_number",
            unique=True, postgresql_where=text("section_id IS NULL"),
        ),
        Index("ix_att_sessions_section_date",  "section_id",      "session_date"),
        Index("ix_att_sessions_semester_date", "semester_id",     "session_date"),
        Index("ix_att_sessions_course_date",   "course_id",       "session_date"),
        Index("ix_att_sessions_faculty_date",  "faculty_user_id", "session_date"),
        Index("ix_att_sessions_status",        "status"),
        Index("ix_att_sessions_date",          "session_date"),
        Index("ix_att_sessions_first_marked",  "first_marked_at"),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Context. NULL section_id means "elective group", not "unknown class".
    course_id        = Column(UUID(as_uuid=True), ForeignKey("courses.id",       ondelete="CASCADE"), nullable=False)
    section_id       = Column(UUID(as_uuid=True), ForeignKey("acad_sections.id", ondelete="CASCADE"), nullable=True)
    # Always set. Without it an elective session could not name its term, since
    # the term was previously only reachable via section -> semester.
    semester_id      = Column(UUID(as_uuid=True), ForeignKey("acad_semesters.id", ondelete="CASCADE"), nullable=False)
    faculty_user_id  = Column(UUID(as_uuid=True), nullable=False)   # plain UUID (no FK — codebase pattern)

    # When
    session_date     = Column(Date,                            nullable=False)
    period_number    = Column(SmallInteger,                    nullable=True)
    duration_minutes = Column(SmallInteger,                    nullable=True)

    # Content
    topic_covered    = Column(Text,                            nullable=True)

    # Lifecycle
    status           = Column(String(10), nullable=False, server_default=text("'OPEN'"))
    first_marked_at  = Column(DateTime(timezone=True),         nullable=True)   # 48h window anchor
    locked_at        = Column(DateTime(timezone=True),         nullable=True)

    # Reopen
    reopened_by      = Column(UUID(as_uuid=True),              nullable=True)
    reopened_at      = Column(DateTime(timezone=True),         nullable=True)
    reopen_reason    = Column(Text,                            nullable=True)

    # Standard audit
    created_at       = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at       = Column(DateTime(timezone=True), nullable=True)

    records = relationship("SisAttendanceRecord", back_populates="session", cascade="all, delete-orphan")


class SisAttendanceRecord(Base):
    __tablename__ = "sis_attendance_records"
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_att_records_session_student"),
        Index("ix_att_records_session",        "session_id"),
        Index("ix_att_records_student",        "student_id"),
        Index("ix_att_records_student_status", "student_id", "status"),
    )

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id  = Column(UUID(as_uuid=True), ForeignKey("sis_attendance_sessions.id", ondelete="CASCADE"), nullable=False)
    student_id  = Column(UUID(as_uuid=True), nullable=False)   # plain UUID (no FK — codebase pattern)

    # Attendance value
    status      = Column(String(10), nullable=False, server_default=text("'ABSENT'"))
    remarks     = Column(Text,       nullable=True)

    # First mark (set when faculty first saves this record)
    marked_by   = Column(UUID(as_uuid=True),          nullable=True)
    marked_at   = Column(DateTime(timezone=True),     nullable=True)

    # Edit tracking (populated only on subsequent edits after first save)
    edited_by   = Column(UUID(as_uuid=True),          nullable=True)
    edited_at   = Column(DateTime(timezone=True),     nullable=True)
    edit_reason = Column(Text,                        nullable=True)

    session = relationship("SisAttendanceSession", back_populates="records")
