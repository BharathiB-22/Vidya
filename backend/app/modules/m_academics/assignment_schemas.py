"""Subject Assignment — Pydantic schemas (H-31)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.modules.m_academics.models import CourseRoleInCourse


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class AssignmentCreate(BaseModel):
    course_id:       UUID
    faculty_user_id: UUID
    semester_id:     UUID
    section_id:      Optional[UUID] = None
    role_in_course:  CourseRoleInCourse = CourseRoleInCourse.PRIMARY


class AssignmentRevokeRequest(BaseModel):
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class CourseInfo(BaseModel):
    id:    UUID
    code:  str
    title: str

    model_config = {"from_attributes": True}


class SemesterInfo(BaseModel):
    id:     UUID
    number: int
    label:  Optional[str]

    model_config = {"from_attributes": True}


class SectionInfo(BaseModel):
    id:   UUID
    name: str

    model_config = {"from_attributes": True}


class FacultyInfo(BaseModel):
    id:        UUID
    full_name: str
    email:     str

    model_config = {"from_attributes": True}


class AssignmentOut(BaseModel):
    id:                  UUID
    course_id:           UUID
    faculty_user_id:     UUID
    semester_id:         UUID
    section_id:          Optional[UUID]
    assigned_by_user_id: UUID
    assigned_at:         datetime
    is_active:           bool
    role_in_course:      CourseRoleInCourse
    revoked_at:          Optional[datetime]
    revoked_by_user_id:  Optional[UUID]

    # Enriched fields populated by service
    course:   Optional[CourseInfo]   = None
    semester: Optional[SemesterInfo] = None
    section:  Optional[SectionInfo]  = None
    faculty:  Optional[FacultyInfo]  = None

    model_config = {"from_attributes": True}


class AssignmentListResponse(BaseModel):
    total:   int
    items:   list[AssignmentOut]


# ---------------------------------------------------------------------------
# Valid semesters for a course — powers the Assign Faculty dialog's picker so
# it can never offer a semester from an unrelated program (see
# AssignmentService.list_valid_semesters).
# ---------------------------------------------------------------------------

class ValidSemesterOut(BaseModel):
    id:           UUID
    number:       int
    label:        Optional[str]
    batch_id:     UUID
    batch_name:   str
    program_id:   UUID
    program_name: str
    program_code: str


class ValidSemestersOut(BaseModel):
    course_id:    UUID
    program_id:   Optional[UUID]
    program_name: Optional[str]
    # False only when the course's curriculum program has no acad_program_id
    # bridge yet — in that case scoping isn't possible and every active
    # semester is returned (mirrors AssignmentService's own permissive policy
    # for the same edge case).
    scoped:       bool
    items:        list[ValidSemesterOut]


# ---------------------------------------------------------------------------
# Courses for an operational semester, each with its (possibly empty) list of
# active assignments — powers the Timetable slot picker: a course with zero
# assignments must still be selectable (faculty saved as null), one with a
# single assignment auto-fills, one with multiple shows a picker.
# ---------------------------------------------------------------------------

class CourseWithAssignmentsOut(BaseModel):
    course_id:   UUID
    code:        str
    title:       str
    assignments: list[AssignmentOut]
    # Teaching load, used by the timetable's Generate action to work out how many
    # weekly periods a course needs. L-T-P are hours per week; older AI-generated
    # courses left them null, so callers fall back to `credits`.
    credits:         int
    hours_lecture:   int | None = None
    hours_tutorial:  int | None = None
    hours_practical: int | None = None
    # An elective choice is taught as one combined class across every section
    # that chose it, so the timetable cell must not claim a single section.
    is_elective:     bool = False
