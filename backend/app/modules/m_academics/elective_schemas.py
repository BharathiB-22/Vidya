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
    # Best-effort — resolved from an active PRIMARY Course Assignment for this
    # course+semester, if one exists yet (assignment is optional, see M01).
    faculty_name: str | None = None


class EligibleElectiveBasketOut(BaseModel):
    basket_id: UUID
    name: str
    description: str | None
    courses: list[EligibleBasketCourseOut]
    already_offered: bool  # an offering already exists for this basket+semester


class ElectiveOfferingCreate(BaseModel):
    basket_id: UUID
    semester_id: UUID
    max_seats: int
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None


class ElectiveOfferingUpdate(BaseModel):
    max_seats: int | None = None
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    status: str | None = None  # OPEN | CLOSED


class ElectiveOfferingPropose(BaseModel):
    basket_id: UUID
    semester_id: UUID
    max_seats: int
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None


class ElectiveRejectBody(BaseModel):
    reason: str


class OfferingCourseOut(BaseModel):
    course_id: UUID
    code: str
    title: str
    credits: int
    description: str | None
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
    proposed_by_user_id: UUID | None = None
    approved_by_user_id: UUID | None = None
    approved_at: datetime | None = None
    published_by_user_id: UUID | None = None
    published_at: datetime | None = None
    rejection_reason: str | None = None


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
