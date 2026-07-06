from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ElectiveOfferingCreate(BaseModel):
    course_id: UUID
    semester_id: UUID
    faculty_user_id: UUID | None = None
    max_seats: int
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None


class ElectiveOfferingUpdate(BaseModel):
    faculty_user_id: UUID | None = None
    max_seats: int | None = None
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    status: str | None = None  # OPEN | CLOSED


class ElectiveOfferingPropose(BaseModel):
    course_id: UUID
    semester_id: UUID
    max_seats: int
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None


class ElectiveRejectBody(BaseModel):
    reason: str


class ElectiveOfferingOut(BaseModel):
    id: UUID
    course_id: UUID
    course_code: str
    course_title: str
    credits: int
    description: str | None
    semester_id: UUID
    faculty_user_id: UUID | None
    faculty_name: str | None
    max_seats: int
    seats_taken: int
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


class ElectiveRegistrationOut(BaseModel):
    id: UUID
    offering_id: UUID
    course_id: UUID
    course_code: str
    course_title: str
    credits: int
    semester_id: UUID
    semester_label: str | None
    faculty_name: str | None
    status: str
    registered_at: datetime
    is_current: bool  # True if the offering's semester is the student's current semester
