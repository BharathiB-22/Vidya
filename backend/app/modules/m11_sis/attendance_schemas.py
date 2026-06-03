"""
SIS Attendance — H55 Pydantic schemas.

Attendance % formula (per H55 policy decisions):
  attended      = COUNT WHERE status IN ('PRESENT', 'LATE')
  total_countable = COUNT WHERE status IN ('PRESENT', 'LATE', 'ABSENT')
                    -- EXCUSED excluded from both numerator and denominator
  pct = ROUND(attended / NULLIF(total_countable, 0) * 100, 2)

Edit window (per H55 policy): 48 hours from first_marked_at (not session created_at).
Edit reason is mandatory on any modification after the first save.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Requests — Faculty
# ---------------------------------------------------------------------------

class SessionCreateIn(BaseModel):
    course_id:        UUID
    section_id:       UUID
    session_date:     date
    period_number:    Optional[int]  = None
    duration_minutes: Optional[int]  = None
    topic_covered:    Optional[str]  = None

    @field_validator("period_number")
    @classmethod
    def valid_period(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 20):
            raise ValueError("period_number must be between 1 and 20")
        return v

    @field_validator("duration_minutes")
    @classmethod
    def valid_duration(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 480):
            raise ValueError("duration_minutes must be between 1 and 480")
        return v


class SessionUpdateIn(BaseModel):
    topic_covered:    Optional[str] = None
    period_number:    Optional[int] = None
    duration_minutes: Optional[int] = None


class AttendanceMarkEntry(BaseModel):
    student_id: UUID
    status:     Literal["PRESENT", "ABSENT", "LATE", "EXCUSED"]
    remarks:    Optional[str] = None


class AttendanceMarkIn(BaseModel):
    records:     list[AttendanceMarkEntry]
    edit_reason: Optional[str] = None   # mandatory (service-enforced) if session already marked


class RecordEditIn(BaseModel):
    status:      Literal["PRESENT", "ABSENT", "LATE", "EXCUSED"]
    remarks:     Optional[str] = None
    edit_reason: Optional[str] = None   # mandatory (service-enforced) if record.marked_by is set


class ReopenSessionIn(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason must not be empty")
        return v.strip()


# ---------------------------------------------------------------------------
# Session output
# ---------------------------------------------------------------------------

class SessionOut(BaseModel):
    id:               UUID
    course_id:        UUID
    course_code:      str
    course_title:     str
    section_id:       UUID
    section_name:     str
    semester_number:  int
    faculty_user_id:  UUID
    faculty_name:     str
    session_date:     date
    period_number:    Optional[int]
    duration_minutes: Optional[int]
    topic_covered:    Optional[str]
    status:           str                  # OPEN | LOCKED
    is_editable:      bool                 # computed: within 48h window and OPEN
    minutes_until_lock: Optional[int]      # countdown; None if not yet marked or locked
    first_marked_at:  Optional[datetime]
    locked_at:        Optional[datetime]
    reopened_by:      Optional[UUID]
    reopened_at:      Optional[datetime]
    reopen_reason:    Optional[str]
    total_enrolled:   int
    present_count:    int
    absent_count:     int
    late_count:       int
    excused_count:    int
    attendance_pct:   Optional[float]      # None if no countable records
    created_at:       datetime
    updated_at:       Optional[datetime]


# ---------------------------------------------------------------------------
# Attendance record output
# ---------------------------------------------------------------------------

class AttendanceRecordOut(BaseModel):
    id:           UUID
    session_id:   UUID
    student_id:   UUID
    student_name: str
    student_email: str
    usn:          Optional[str]
    status:       str
    remarks:      Optional[str]
    marked_by:    Optional[UUID]
    marked_at:    Optional[datetime]
    edited_by:    Optional[UUID]
    edited_at:    Optional[datetime]
    edit_reason:  Optional[str]


# ---------------------------------------------------------------------------
# Mark result
# ---------------------------------------------------------------------------

class AttendanceMarkResult(BaseModel):
    session_id:    UUID
    saved:         int
    first_marks:   int
    edits:         int


# ---------------------------------------------------------------------------
# Student self-view
# ---------------------------------------------------------------------------

class CourseAttendanceSummary(BaseModel):
    course_id:          UUID
    course_code:        str
    course_title:       str
    total_sessions:     int            # total sessions for this course+section
    attended_sessions:  int            # PRESENT + LATE
    excused_sessions:   int
    total_countable:    int            # total - excused
    attendance_pct:     Optional[float]  # None if no countable sessions
    is_at_risk:         bool           # advisory; pct < threshold and total_countable > 0


class MyAttendanceSummary(BaseModel):
    student_id:    UUID
    student_name:  str
    usn:           Optional[str]
    overall_pct:   Optional[float]
    courses:       list[CourseAttendanceSummary]


class SessionRecordForStudent(BaseModel):
    session_id:      UUID
    session_date:    date
    period_number:   Optional[int]
    topic_covered:   Optional[str]
    status:          str
    remarks:         Optional[str]


class MyCourseAttendanceDetail(BaseModel):
    course_id:    UUID
    course_code:  str
    course_title: str
    summary:      CourseAttendanceSummary
    sessions:     list[SessionRecordForStudent]


# ---------------------------------------------------------------------------
# Section analytics
# ---------------------------------------------------------------------------

class SectionStudentAttendance(BaseModel):
    student_id:         UUID
    student_name:       str
    usn:                Optional[str]
    total_sessions:     int
    attended_sessions:  int
    total_countable:    int
    attendance_pct:     Optional[float]
    is_at_risk:         bool


class SectionAttendanceOut(BaseModel):
    section_id:        UUID
    section_name:      str
    semester_number:   int
    batch_name:        str
    program_name:      str
    total_sessions:    int
    avg_attendance_pct: Optional[float]
    students:          list[SectionStudentAttendance]


# ---------------------------------------------------------------------------
# Shortage report (Dean / Admin analytics)
# ---------------------------------------------------------------------------

class ShortageStudentOut(BaseModel):
    student_id:        UUID
    student_name:      str
    usn:               Optional[str]
    email:             str
    section_id:        UUID
    section_name:      str
    course_id:         UUID
    course_code:       str
    course_title:      str
    total_sessions:    int
    attended_sessions: int
    total_countable:   int
    attendance_pct:    float


class ShortageReportOut(BaseModel):
    threshold_pct:  float
    total_at_risk:  int
    finalized_only: bool = False
    students:       list[ShortageStudentOut]


# ---------------------------------------------------------------------------
# Faculty-scoped shortage report (H56)
# ---------------------------------------------------------------------------

class FacultyCourseShortage(BaseModel):
    course_id:       UUID
    course_code:     str
    course_title:    str
    section_id:      UUID
    section_name:    str
    semester_number: int
    at_risk_count:   int
    total_enrolled:  int
    students:        list[ShortageStudentOut]


class FacultyShortageReportOut(BaseModel):
    faculty_id:     UUID
    threshold_pct:  float
    finalized_only: bool
    total_at_risk:  int
    courses:        list[FacultyCourseShortage]


# ---------------------------------------------------------------------------
# Grouped shortage report — Dean / Admin (H56)
# ---------------------------------------------------------------------------

class ShortageSectionGroup(BaseModel):
    section_id:      UUID
    section_name:    str
    semester_number: int
    at_risk_count:   int
    avg_pct:         Optional[float]
    students:        list[ShortageStudentOut]


class ShortageCourseGroup(BaseModel):
    course_id:    UUID
    course_code:  str
    course_title: str
    total_at_risk: int
    sections:     list[ShortageSectionGroup]


class ShortageGroupedOut(BaseModel):
    threshold_pct:               float
    finalized_only:              bool
    total_courses_with_shortage: int
    total_students_at_risk:      int
    courses:                     list[ShortageCourseGroup]


# ---------------------------------------------------------------------------
# Dashboard (Dean / Admin)
# ---------------------------------------------------------------------------

class AttendanceDashboardOut(BaseModel):
    today_sessions:           int
    marked_today:             int    # sessions today with first_marked_at IS NOT NULL
    pending_sessions:         int    # past sessions with first_marked_at IS NULL
    students_below_threshold: int
    threshold_pct:            float
