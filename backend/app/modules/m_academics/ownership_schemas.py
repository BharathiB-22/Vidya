"""Academic Ownership & Responsibility — Pydantic schemas (Phase B)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared info blocks
# ---------------------------------------------------------------------------

class DeptInfo(BaseModel):
    id:   UUID
    name: str
    code: str
    model_config = {"from_attributes": True}


class ProgramInfo(BaseModel):
    id:             UUID
    name:           str
    code:           str
    degree_type:    str
    department:     Optional[DeptInfo] = None
    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Faculty program-scope assignment (faculty_program_assignments extended)
# ---------------------------------------------------------------------------

class FacultyProgramAssignCreate(BaseModel):
    faculty_user_id: UUID
    program_id:      UUID
    is_primary:      bool = False
    semester_id:     Optional[UUID] = None
    section_id:      Optional[UUID] = None


class FacultyProgramAssignOut(BaseModel):
    id:              UUID
    faculty_user_id: UUID
    program_id:      UUID
    department_id:   Optional[UUID]
    semester_id:     Optional[UUID]
    section_id:      Optional[UUID]
    is_primary:      bool
    is_active:       bool
    assigned_by:     UUID
    assigned_at:     datetime
    revoked_by:      Optional[UUID]
    revoked_at:      Optional[datetime]
    # Enriched
    program_name:    Optional[str] = None
    department_name: Optional[str] = None
    faculty_name:    Optional[str] = None
    faculty_email:   Optional[str] = None
    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Faculty "My Academic Responsibilities"
# ---------------------------------------------------------------------------

class FacultyResponsibilityProgram(BaseModel):
    id:             UUID
    name:           str
    code:           str
    degree_type:    str
    department:     Optional[DeptInfo]
    is_primary:     bool
    assigned_by_name: Optional[str]
    assigned_at:    datetime


class FacultyCourseEntry(BaseModel):
    assignment_id:  UUID
    course_id:      UUID
    code:           str
    title:          str
    semester_number: int
    semester_label: Optional[str]
    section_name:   Optional[str]
    role_in_course: str
    is_active:      bool


class FacultyAcademicResponsibilities(BaseModel):
    faculty_user_id:  UUID
    departments:      list[DeptInfo]
    programs:         list[FacultyResponsibilityProgram]
    course_assignments: list[FacultyCourseEntry]


class FacultyAcademicSummary(BaseModel):
    course_count:     int
    program_count:    int
    department_count: int


# ---------------------------------------------------------------------------
# Dean governed programs
# ---------------------------------------------------------------------------

class DeanProgramOut(BaseModel):
    id:                  UUID
    name:                str
    code:                str
    degree_type:         str
    department:          Optional[DeptInfo]
    active_faculty_count: int


# ---------------------------------------------------------------------------
# Faculty workload (for dean faculty page)
# ---------------------------------------------------------------------------

class FacultyWorkloadItem(BaseModel):
    faculty_user_id: UUID
    course_count:    int
    program_count:   int


class FacultyWorkloadResponse(BaseModel):
    items: list[FacultyWorkloadItem]


# ---------------------------------------------------------------------------
# Ownership Matrix
# ---------------------------------------------------------------------------

class MatrixFaculty(BaseModel):
    user_id:        UUID
    full_name:      str
    role_in_course: str


class MatrixCourse(BaseModel):
    course_id:   UUID
    code:        str
    title:       str
    course_type: Optional[str]
    faculty:     list[MatrixFaculty]


class MatrixSemester(BaseModel):
    semester_id: UUID
    number:      int
    label:       Optional[str]
    courses:     list[MatrixCourse]


class MatrixProgram(BaseModel):
    program_id:  UUID
    name:        str
    code:        str
    department:  Optional[DeptInfo]
    semesters:   list[MatrixSemester]


class OwnershipMatrixOut(BaseModel):
    programs: list[MatrixProgram]
