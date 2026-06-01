"""
SIS Enrollment — M11-002 Pydantic schemas.

No new tables.  All operations run against the existing:
  acad_enrollments, acad_sections, acad_semesters, acad_batches,
  acad_programs, acad_departments, sis_schools, users (STUDENT role).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class EnrollStudentIn(BaseModel):
    student_id: UUID
    section_id: UUID


class MoveStudentIn(BaseModel):
    target_section_id: UUID


# ---------------------------------------------------------------------------
# Enrollment record
# ---------------------------------------------------------------------------

class EnrollmentOut(BaseModel):
    id: UUID
    student_id: UUID
    section_id: UUID
    enrolled_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Roster (section-level student list with user details)
# ---------------------------------------------------------------------------

class RosterStudentOut(BaseModel):
    enrollment_id: UUID
    student_id: UUID
    full_name: str
    email: str
    identifier: Optional[str]
    enrolled_at: datetime
    is_active: bool


# ---------------------------------------------------------------------------
# Student list (for enroll-student picker)
# ---------------------------------------------------------------------------

class StudentSummaryOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    identifier: Optional[str]
    is_enrolled: bool


# ---------------------------------------------------------------------------
# Student academic profile
# ---------------------------------------------------------------------------

class ProgramSummary(BaseModel):
    id: UUID
    name: str
    code: str
    degree_type: str


class DeptSummary(BaseModel):
    id: UUID
    name: str
    code: str


class BatchSummary(BaseModel):
    id: UUID
    name: str
    start_year: int
    end_year: int


class SemesterSummary(BaseModel):
    id: UUID
    number: int
    label: Optional[str]


class SectionSummary(BaseModel):
    id: UUID
    name: str


class EnrollmentSummary(BaseModel):
    enrollment_id: UUID
    section: SectionSummary
    semester: SemesterSummary


class StudentProfileOut(BaseModel):
    student_id: UUID
    full_name: str
    email: str
    identifier: Optional[str]
    program: Optional[ProgramSummary]
    department: Optional[DeptSummary]
    batch: Optional[BatchSummary]
    enrollment: Optional[EnrollmentSummary]


# ---------------------------------------------------------------------------
# SIS Dashboard counts
# ---------------------------------------------------------------------------

class DashboardCountsOut(BaseModel):
    schools: int
    departments: int
    programs: int
    active_batches: int
    semesters: int
    sections: int
    enrolled_students: int
