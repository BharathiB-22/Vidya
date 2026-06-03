"""
SIS Directory — H50 Pydantic schemas.

Student and Faculty directory: paginated listings, full profile views,
and upsert request bodies for profile management.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Generic, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, field_validator

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Shared mini-summaries (reused across student and faculty schemas)
# ---------------------------------------------------------------------------

class ProgramMini(BaseModel):
    id: UUID
    name: str
    code: str
    degree_type: str


class DeptMini(BaseModel):
    id: UUID
    name: str
    code: str


class BatchMini(BaseModel):
    id: UUID
    name: str
    start_year: int
    end_year: int


class SectionMini(BaseModel):
    id: UUID
    name: str


class CourseMini(BaseModel):
    id: UUID
    name: str
    code: str


class AssignmentMini(BaseModel):
    course: CourseMini
    semester_label: str
    role: str


# ---------------------------------------------------------------------------
# Paginated wrapper
# ---------------------------------------------------------------------------

class DirectoryPage(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------------------------------------------------------------------------
# Student directory — list card
# ---------------------------------------------------------------------------

class StudentDirectoryItem(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    identifier: Optional[str]
    usn: Optional[str]
    admission_year: Optional[int]
    program: Optional[ProgramMini]
    department: Optional[DeptMini]
    batch: Optional[BatchMini]
    current_section: Optional[SectionMini]
    is_active: bool


# ---------------------------------------------------------------------------
# Student profile — full detail (used in GET /directory/students/{id})
# ---------------------------------------------------------------------------

class StudentDetailOut(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    identifier: Optional[str]
    usn: Optional[str]
    admission_year: Optional[int]
    date_of_birth: Optional[date]
    phone: Optional[str]
    address_line1: Optional[str]
    address_city: Optional[str]
    address_state: Optional[str]
    emergency_contact_name: Optional[str]
    emergency_contact_phone: Optional[str]
    photo_url: Optional[str]
    notes: Optional[str]
    program: Optional[ProgramMini]
    department: Optional[DeptMini]
    batch: Optional[BatchMini]
    current_section: Optional[SectionMini]
    is_active: bool
    profile_created_at: Optional[datetime]
    profile_updated_at: Optional[datetime]


# ---------------------------------------------------------------------------
# Student profile upsert request
# ---------------------------------------------------------------------------

class StudentProfileUpsert(BaseModel):
    usn: Optional[str] = None
    admission_year: Optional[int] = None
    date_of_birth: Optional[date] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_city: Optional[str] = None
    address_state: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    photo_url: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("usn", mode="before")
    @classmethod
    def strip_usn(cls, v: Optional[str]) -> Optional[str]:
        if not isinstance(v, str):
            return v
        stripped = v.strip()
        return stripped.upper() if stripped else None

    @field_validator("admission_year", mode="after")
    @classmethod
    def valid_year(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1900 < v < 2100):
            raise ValueError("admission_year must be a valid calendar year")
        return v


# ---------------------------------------------------------------------------
# Faculty directory — list card
# ---------------------------------------------------------------------------

class FacultyDirectoryItem(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    employee_id: Optional[str]
    designation: Optional[str]
    specialization: Optional[str]
    primary_department: Optional[DeptMini]
    photo_url: Optional[str]
    is_active: bool


# ---------------------------------------------------------------------------
# Faculty profile — full detail (used in GET /directory/faculty/{id})
# ---------------------------------------------------------------------------

class FacultyDetailOut(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    identifier: Optional[str]
    employee_id: Optional[str]
    designation: Optional[str]
    qualifications: Optional[str]
    bio: Optional[str]
    office_location: Optional[str]
    phone: Optional[str]
    joining_date: Optional[date]
    specialization: Optional[str]
    primary_department: Optional[DeptMini]
    photo_url: Optional[str]
    active_assignments: list[AssignmentMini]
    is_active: bool
    profile_created_at: Optional[datetime]
    profile_updated_at: Optional[datetime]


# ---------------------------------------------------------------------------
# Faculty profile upsert request
# ---------------------------------------------------------------------------

class FacultyProfileUpsert(BaseModel):
    employee_id: str
    designation: Optional[str] = None
    qualifications: Optional[str] = None
    bio: Optional[str] = None
    office_location: Optional[str] = None
    phone: Optional[str] = None
    joining_date: Optional[date] = None
    specialization: Optional[str] = None
    primary_department_id: Optional[UUID] = None
    photo_url: Optional[str] = None

    @field_validator("employee_id", mode="before")
    @classmethod
    def strip_employee_id(cls, v: str) -> str:
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("employee_id", mode="after")
    @classmethod
    def non_empty_employee_id(cls, v: str) -> str:
        if not v:
            raise ValueError("employee_id must not be empty")
        return v


# ---------------------------------------------------------------------------
# H51: Self-service schemas — students and faculty editing own contact details
# Fields NOT present here cannot be changed by the user themselves.
# ---------------------------------------------------------------------------

class StudentSelfServiceUpdate(BaseModel):
    """Fields a STUDENT is allowed to update on their own profile."""
    phone:                   Optional[str] = None
    address_line1:           Optional[str] = None
    address_city:            Optional[str] = None
    address_state:           Optional[str] = None
    emergency_contact_name:  Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    photo_url:               Optional[str] = None


class FacultySelfServiceUpdate(BaseModel):
    """Fields a FACULTY member is allowed to update on their own profile."""
    phone:           Optional[str] = None
    office_location: Optional[str] = None
    bio:             Optional[str] = None
    specialization:  Optional[str] = None
    photo_url:       Optional[str] = None
