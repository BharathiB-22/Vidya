from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.m01_program_advisor.models import ProgramStatus


# ---------------------------------------------------------------------------
# Course prerequisite schemas
# ---------------------------------------------------------------------------

class CoursePrerequisiteCreate(BaseModel):
    prerequisite_course_id: UUID


class CoursePrerequisiteResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:                     UUID
    course_id:              UUID
    prerequisite_course_id: UUID


# ---------------------------------------------------------------------------
# Course schemas
# ---------------------------------------------------------------------------

class CourseCreate(BaseModel):
    code:                    str
    title:                   str
    credits:                 int = Field(..., ge=1)
    semester:                int = Field(..., ge=1)
    is_elective:             bool = False
    hours_lecture:           Optional[int] = None
    hours_tutorial:          Optional[int] = None
    hours_practical:         Optional[int] = None
    description:             Optional[str] = None
    prerequisite_course_ids: list[UUID] = []


class CourseUpdate(BaseModel):
    code:            Optional[str] = None
    title:           Optional[str] = None
    credits:         Optional[int] = Field(default=None, ge=1)
    semester:        Optional[int] = Field(default=None, ge=1)
    is_elective:     Optional[bool] = None
    hours_lecture:   Optional[int] = None
    hours_tutorial:  Optional[int] = None
    hours_practical: Optional[int] = None
    description:     Optional[str] = None


class CourseResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:              UUID
    program_id:      UUID
    code:            str
    title:           str
    credits:         int
    semester:        int
    is_elective:     bool
    is_ai_generated: bool
    hours_lecture:   Optional[int]
    hours_tutorial:  Optional[int]
    hours_practical: Optional[int]
    description:     Optional[str]
    created_at:      datetime
    updated_at:      Optional[datetime]


# ---------------------------------------------------------------------------
# Program outcome schemas
# ---------------------------------------------------------------------------

class ProgramOutcomeCreate(BaseModel):
    code:          str
    description:   str
    bloom_level:   Optional[str] = None
    display_order: int = 0


class ProgramOutcomeUpdate(BaseModel):
    code:          Optional[str] = None
    description:   Optional[str] = None
    bloom_level:   Optional[str] = None
    display_order: Optional[int] = None


class ProgramOutcomeResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:            UUID
    program_id:    UUID
    code:          str
    description:   str
    bloom_level:   Optional[str]
    display_order: int
    created_at:    datetime


# ---------------------------------------------------------------------------
# Program schemas
# ---------------------------------------------------------------------------

class ProgramCreate(BaseModel):
    title:            str
    degree_type:      str
    department:       str
    duration_years:   int = Field(..., ge=1)
    total_credits:    int = Field(..., ge=1)
    acad_program_id:  Optional[UUID] = None
    outcomes:         list[ProgramOutcomeCreate] = []
    courses:          list[CourseCreate] = []


class ProgramUpdate(BaseModel):
    title:           Optional[str] = None
    degree_type:     Optional[str] = None
    department:      Optional[str] = None
    duration_years:  Optional[int] = Field(default=None, ge=1)
    total_credits:   Optional[int] = Field(default=None, ge=1)
    acad_program_id: Optional[UUID] = None


class ProgramResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:                  UUID
    version:             int
    parent_version_id:   Optional[UUID]
    title:               str
    degree_type:         str
    department:          str
    duration_years:      int
    total_credits:       int
    status:              ProgramStatus
    acad_program_id:     Optional[UUID]
    ai_model:            Optional[str]
    prompt_hash:         Optional[str]
    approved_by_user_id: Optional[UUID]
    approved_at:         Optional[datetime]
    created_by_user_id:  UUID
    created_at:          datetime
    updated_at:          Optional[datetime]


class ProgramDetail(ProgramResponse):
    outcomes: list[ProgramOutcomeResponse]
    courses:  list[CourseResponse]


class ProgramListResponse(BaseModel):
    total:     int
    page:      int
    page_size: int
    items:     list[ProgramResponse]


class ProgramVersionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:                UUID
    version:           int
    parent_version_id: Optional[UUID]
    title:             str
    status:            ProgramStatus
    created_by_user_id: UUID
    created_at:        datetime


# ---------------------------------------------------------------------------
# Approval / status schemas
# ---------------------------------------------------------------------------

class ApproveRequest(BaseModel):
    comment: Optional[str] = None


class RejectRequest(BaseModel):
    reason: str


class ProgramStatusResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:         UUID
    status:     ProgramStatus
    updated_at: Optional[datetime]


# ---------------------------------------------------------------------------
# AI generation schemas
# ---------------------------------------------------------------------------

class GenerateProgramRequest(BaseModel):
    prompt_hint: Optional[str] = Field(
        default=None,
        description="Optional guidance for the AI generator (e.g. 'focus on industry-aligned electives')",
    )


class ProgramAIJobResponse(BaseModel):
    job_id:     UUID
    program_id: UUID
    status:     str = "queued"


# ---------------------------------------------------------------------------
# Compliance response schemas
# ---------------------------------------------------------------------------

class ComplianceViolationResponse(BaseModel):
    rule_id:  str
    rule_ref: str
    message:  str
    severity: str   # "ERROR" | "WARNING"


class ComplianceResultResponse(BaseModel):
    passed:     bool
    violations: list[ComplianceViolationResponse]


# ---------------------------------------------------------------------------
# Export schemas
# ---------------------------------------------------------------------------

class ProgramExportJobResponse(BaseModel):
    job_id:     UUID
    program_id: UUID
    format:     str
    status:     str = "queued"
