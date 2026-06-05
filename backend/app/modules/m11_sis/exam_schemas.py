"""
SIS Examination Management — H59 Pydantic schemas.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ── Exam Center ────────────────────────────────────────────────────────────

class ExamCenterCreateIn(BaseModel):
    center_code: str = Field(min_length=1, max_length=20)
    center_name: str = Field(min_length=1, max_length=200)
    address:     Optional[str] = None
    capacity:    Optional[int] = Field(None, ge=1)
    is_internal: bool = True
    is_active:   bool = True


class ExamCenterUpdateIn(BaseModel):
    center_name: Optional[str] = Field(None, min_length=1, max_length=200)
    address:     Optional[str] = None
    capacity:    Optional[int] = Field(None, ge=1)
    is_internal: Optional[bool] = None
    is_active:   Optional[bool] = None


class ExamCenterOut(BaseModel):
    id:          UUID
    center_code: str
    center_name: str
    address:     Optional[str]
    capacity:    Optional[int]
    is_internal: bool
    is_active:   bool
    created_at:  datetime
    updated_at:  Optional[datetime]
    model_config = ConfigDict(from_attributes=True)


# ── Exam Session ───────────────────────────────────────────────────────────

SessionType = Literal["REGULAR", "SUPPLEMENTARY", "REVALUATION", "IMPROVEMENT"]
SessionStatus = Literal[
    "DRAFT", "PUBLISHED", "SEATING_ALLOCATED", "LOCKED", "COMPLETED"
]


class ExamSessionCreateIn(BaseModel):
    semester_id:            UUID
    session_type:           SessionType
    session_name:           str = Field(min_length=3, max_length=100)
    academic_year:          str = Field(min_length=4, max_length=20)
    start_date:             date
    end_date:               date
    notes:                  Optional[str] = None
    source_exam_session_id: Optional[UUID] = None
    attempt_number:         Optional[int] = Field(None, ge=1, le=10)

    @model_validator(mode="after")
    def end_on_or_after_start(self) -> "ExamSessionCreateIn":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class ExamSessionUpdateIn(BaseModel):
    session_name:  Optional[str]  = Field(None, min_length=3, max_length=100)
    academic_year: Optional[str]  = None
    start_date:    Optional[date] = None
    end_date:      Optional[date] = None
    notes:         Optional[str]  = None


class ExamSessionOut(BaseModel):
    id:                      UUID
    semester_id:             UUID
    session_type:            str
    session_name:            str
    academic_year:           str
    start_date:              date
    end_date:                date
    status:                  str
    notes:                   Optional[str]
    source_exam_session_id:  Optional[UUID]
    attempt_number:          Optional[int]
    hall_ticket_generated_at: Optional[datetime]
    hall_ticket_generated_by: Optional[UUID]
    created_by:              UUID
    created_at:              datetime
    updated_at:              Optional[datetime]
    schedule_count:          int = 0
    model_config = ConfigDict(from_attributes=True)


# ── Exam Schedule ──────────────────────────────────────────────────────────

class ExamScheduleCreateIn(BaseModel):
    course_id:   UUID
    section_id:  UUID
    center_id:   Optional[UUID]  = None
    exam_date:   date
    start_time:  time
    end_time:    time
    room_number: Optional[str]  = Field(None, max_length=30)
    notes:       Optional[str]  = None

    @model_validator(mode="after")
    def end_after_start(self) -> "ExamScheduleCreateIn":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class ExamScheduleUpdateIn(BaseModel):
    center_id:   Optional[UUID] = None
    exam_date:   Optional[date] = None
    start_time:  Optional[time] = None
    end_time:    Optional[time] = None
    room_number: Optional[str] = Field(None, max_length=30)
    notes:       Optional[str] = None


class ExamScheduleOut(BaseModel):
    id:           UUID
    session_id:   UUID
    course_id:    UUID
    course_code:  str
    course_title: str
    section_id:   UUID
    section_name: str
    center_id:    Optional[UUID]
    center_name:  Optional[str]
    exam_date:    date
    start_time:   time
    end_time:     time
    room_number:  Optional[str]
    notes:        Optional[str]
    created_by:   UUID
    created_at:   datetime
    updated_at:   Optional[datetime]
    model_config = ConfigDict(from_attributes=True)


# ── Invigilation ───────────────────────────────────────────────────────────

class InvigilationCreateIn(BaseModel):
    schedule_id:     Optional[UUID] = None
    center_id:       Optional[UUID] = None
    room_number:     Optional[str]  = Field(None, max_length=30)
    faculty_user_id: UUID
    notes:           Optional[str]  = None


class InvigilationOut(BaseModel):
    id:              UUID
    session_id:      UUID
    schedule_id:     Optional[UUID]
    center_id:       Optional[UUID]
    center_name:     Optional[str]
    room_number:     Optional[str]
    faculty_user_id: UUID
    faculty_name:    Optional[str]
    assigned_by:     UUID
    notes:           Optional[str]
    created_at:      datetime
    # enriched from schedule join
    exam_date:       Optional[date]     = None
    start_time:      Optional[time]     = None
    end_time:        Optional[time]     = None
    model_config = ConfigDict(from_attributes=True)


# ── Seat Allocation ────────────────────────────────────────────────────────

class RoomSpec(BaseModel):
    room_number: str = Field(min_length=1, max_length=30)
    capacity:    int = Field(ge=1)


class SeatAllocationIn(BaseModel):
    center_id:  UUID
    rooms:      List[RoomSpec] = Field(min_length=1)
    section_id: Optional[UUID] = None


class RoomAllocationDetail(BaseModel):
    room_number: str
    capacity:    int
    assigned:    int


class SeatingAllocationResult(BaseModel):
    session_id:     UUID
    allocated:      int
    rooms_used:     int
    total_capacity: int
    details:        List[RoomAllocationDetail]


class StudentSeatOut(BaseModel):
    student_id:         UUID
    student_name:       Optional[str]
    usn:                Optional[str]
    hall_ticket_number: Optional[str]
    section_name:       Optional[str]
    center_name:        Optional[str]
    room_number:        Optional[str]
    seat_number:        Optional[str]
    model_config = ConfigDict(from_attributes=True)


# ── Student views ──────────────────────────────────────────────────────────

class CourseScheduleRow(BaseModel):
    course_id:    UUID
    course_code:  str
    course_title: str
    exam_date:    Optional[date]
    start_time:   Optional[time]
    end_time:     Optional[time]
    center_name:  Optional[str]
    room_number:  Optional[str]
    is_scheduled: bool


class SeatInfo(BaseModel):
    center_name: str
    address:     Optional[str]
    room_number: str
    seat_number: str


class StudentTimetableOut(BaseModel):
    session_id:   UUID
    session_name: str
    session_type: str
    semester_name: str
    seat:         Optional[SeatInfo]
    courses:      List[CourseScheduleRow]


class MyHallTicketExamOut(BaseModel):
    hall_ticket_number: str
    student_id:         UUID
    student_name:       Optional[str]
    usn:                Optional[str]
    semester_name:      str
    academic_year:      str
    status:             str
    seat:               Optional[SeatInfo]
    timetable:          List[CourseScheduleRow]
    issued_at:          Optional[datetime]
    exam_session_id:    Optional[UUID]
    model_config = ConfigDict(from_attributes=True)
