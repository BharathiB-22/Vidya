from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class EligibleBasketCourseOut(BaseModel):
    course_id: UUID
    code: str
    title: str
    credits: int
    description: str | None
    # The currently-assigned PRIMARY faculty for this course+semester, if any.
    faculty_user_id: UUID | None = None
    faculty_name: str | None = None


class EligibleElectiveBasketOut(BaseModel):
    basket_id: UUID
    name: str
    description: str | None
    courses: list[EligibleBasketCourseOut]
    already_offered: bool  # an offering already exists for this basket+semester


class OfferingFacultyAssignment(BaseModel):
    """The Dean's choice of which faculty teaches one course inside the basket.
    Applied as a PRIMARY Course Assignment so attendance/marks pick it up."""
    course_id: UUID
    faculty_user_id: UUID


class ElectiveOfferingCreate(BaseModel):
    basket_id: UUID
    semester_id: UUID
    max_seats: int
    faculty_assignments: list[OfferingFacultyAssignment] | None = None
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None


class ElectiveOfferingUpdate(BaseModel):
    max_seats: int | None = None
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    status: str | None = None  # OPEN | CLOSED


class AssignFacultyBody(BaseModel):
    course_id: UUID
    faculty_user_id: UUID


class OfferingCourseOut(BaseModel):
    course_id: UUID
    code: str
    title: str
    credits: int
    description: str | None
    faculty_user_id: UUID | None = None
    faculty_name: str | None = None
    seats_taken: int


class ElectiveOfferingOut(BaseModel):
    id: UUID
    basket_id: UUID
    basket_name: str
    basket_description: str | None
    semester_id: UUID
    max_seats: int
    courses: list[OfferingCourseOut]
    registration_opens_at: datetime | None
    registration_closes_at: datetime | None
    status: str
    created_at: datetime


class DeanElectiveStatsOut(BaseModel):
    total_offerings: int
    total_registrations: int
    offerings: list[ElectiveOfferingOut]


class ElectiveRegisterBody(BaseModel):
    course_id: UUID  # the ONE course, from within the basket, the student picks


class ElectiveRegistrationOut(BaseModel):
    id: UUID
    offering_id: UUID
    basket_id: UUID
    basket_name: str
    course_id: UUID
    course_code: str
    course_title: str
    credits: int
    semester_id: UUID
    semester_label: str | None
    status: str
    registered_at: datetime
    is_current: bool  # True if the offering's semester is the student's current semester


# ---------------------------------------------------------------------------
# Faculty roster — the students who chose THIS faculty's elective course.
# ---------------------------------------------------------------------------

class ElectiveRosterStudentOut(BaseModel):
    student_id: UUID
    student_name: str
    usn: str | None = None
    student_email: str | None = None
    registered_at: datetime


class FacultyElectiveRosterOut(BaseModel):
    course_id: UUID
    course_code: str
    course_title: str
    offering_id: UUID
    semester_id: UUID
    semester_label: str | None
    basket_name: str
    total_students: int
    students: list[ElectiveRosterStudentOut]
