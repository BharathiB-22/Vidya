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
    # How this program entered the faculty's scope:
    #   APPOINTED — explicit faculty_program_assignments grant (coordinator / membership)
    #   TEACHING  — implied purely by courses the faculty teaches in this program
    source:         str = "TEACHING"


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
    # Resolved strictly via Course -> Semester -> Program -> Department so the
    # UI can nest a course under its real program/department instead of
    # rendering it disconnected from the Programs/Departments sections.
    program_id:      Optional[UUID] = None
    program_name:    Optional[str] = None
    program_code:    Optional[str] = None
    department_id:   Optional[UUID] = None
    department_name: Optional[str] = None


class FacultyAcademicResponsibilities(BaseModel):
    faculty_user_id:  UUID
    # The faculty's own home department (sis_faculty_profiles.primary_department_id),
    # distinct from departments derived from program/course scope below.
    home_department:  Optional[DeptInfo] = None
    # Active responsibility grants (GUIDE / EVALUATOR / BOARD) plus DEAN when the
    # base login role is DEAN — the "hats" a single login carries.
    responsibilities: list[str] = []
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
# Ownership Matrix — Department -> Program -> Semester -> Section -> Course -> Faculty
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


# A `None` section_id/name is the "General" bucket: courses assigned at the
# whole-semester level (subject_assignments.section_id IS NULL) rather than
# to one specific acad_section.
class MatrixSection(BaseModel):
    section_id: Optional[UUID]
    name:       str
    courses:    list[MatrixCourse]


class MatrixSemester(BaseModel):
    semester_id: UUID
    number:      int
    label:       Optional[str]
    sections:    list[MatrixSection]


class MatrixProgram(BaseModel):
    program_id:  UUID
    name:        str
    code:        str
    department:  Optional[DeptInfo]
    semesters:   list[MatrixSemester]


class MatrixDepartment(BaseModel):
    department_id: Optional[UUID]
    name:          str
    code:          Optional[str]
    programs:      list[MatrixProgram]


class OwnershipMatrixOut(BaseModel):
    departments: list[MatrixDepartment]


# ---------------------------------------------------------------------------
# Ownership dashboard summary — existing data only, no new states
# ---------------------------------------------------------------------------

class DashboardFacultyWorkload(BaseModel):
    faculty_user_id: UUID
    faculty_name:    str
    course_count:    int
    program_count:   int


class OwnershipDashboardSummary(BaseModel):
    total_programs:    int
    total_courses:     int
    total_faculty:     int
    vacant_courses:    int
    program_coverage_pct: float  # % of courses (across governed programs) with an active PRIMARY faculty
    faculty_workload:  list[DashboardFacultyWorkload]
