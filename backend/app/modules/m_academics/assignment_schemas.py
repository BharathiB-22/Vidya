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
