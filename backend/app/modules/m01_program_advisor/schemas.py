from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.m01_program_advisor.models import CourseType, ProgramStatus


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
    course_type:             Optional[CourseType] = None
    is_elective:             bool = False
    elective_basket_id:      Optional[UUID] = None
    hours_lecture:           Optional[int] = None
    hours_tutorial:          Optional[int] = None
    hours_practical:         Optional[int] = None
    description:             Optional[str] = None
    prerequisite_course_ids: list[UUID] = []


class CourseUpdate(BaseModel):
    code:               Optional[str] = None
    title:              Optional[str] = None
    credits:            Optional[int] = Field(default=None, ge=1)
    semester:           Optional[int] = Field(default=None, ge=1)
    course_type:        Optional[CourseType] = None
    is_elective:        Optional[bool] = None
    elective_basket_id: Optional[UUID] = None
    hours_lecture:      Optional[int] = None
    hours_tutorial:     Optional[int] = None
    hours_practical:    Optional[int] = None
    description:        Optional[str] = None


class CourseResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:                 UUID
    program_id:         UUID
    code:               str
    title:              str
    credits:            int
    semester:           int
    course_type:        Optional[CourseType]
    is_elective:        bool
    elective_basket_id: Optional[UUID]
    is_ai_generated:    bool
    hours_lecture:      Optional[int]
    hours_tutorial:     Optional[int]
    hours_practical:    Optional[int]
    description:        Optional[str]
    created_at:         datetime
    updated_at:         Optional[datetime]


# ---------------------------------------------------------------------------
# Elective Basket schemas — ONE curriculum elective slot (e.g. "Elective 1",
# 3 credits, Semester 3) holding any number of interchangeable option courses
# (AI301, DM301, DL301, ...). The slot owns the credits; a student takes
# exactly one option, so the slot counts once toward the curriculum.
# ---------------------------------------------------------------------------

class ElectiveBasketCreate(BaseModel):
    semester:    int = Field(..., ge=1)
    name:        str
    credits:     int = Field(3, ge=1, le=6)
    description: Optional[str] = None


class ElectiveBasketUpdate(BaseModel):
    name:        Optional[str] = None
    credits:     Optional[int] = Field(None, ge=1, le=6)
    description: Optional[str] = None


class ElectiveChoiceCreate(BaseModel):
    """One interchangeable option inside a slot.

    There is no `code`: the server generates it (see course_codes.py), and no
    `semester`: an option always sits in its slot's semester. `credits` defaults
    to the slot's own weight, because a student earns the slot's credits
    whichever option they take.
    """
    title:       str
    credits:     Optional[int] = Field(None, ge=1, le=6)
    course_type: Optional[CourseType] = None
    description: Optional[str] = None


class ElectiveBasketCourseOut(BaseModel):
    model_config = {"from_attributes": True}

    id:          UUID
    code:        str
    title:       str
    credits:     int
    semester:    int
    course_type: Optional[CourseType] = None


class ElectiveBasketResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:          UUID
    program_id:  UUID
    semester:    int
    name:        str
    credits:     int
    description: Optional[str]
    # Slot lifecycle: DRAFT -> PUBLISHED -> OPEN -> CLOSED. Choices are editable
    # only while DRAFT; students may register only while OPEN.
    status:                 str
    published_at:           Optional[datetime] = None
    registration_opened_at: Optional[datetime] = None
    registration_closed_at: Optional[datetime] = None
    created_at:  datetime
    updated_at:  Optional[datetime]
    courses:     list[ElectiveBasketCourseOut] = []


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
    ai_instructions:  Optional[str] = None
    # A curriculum version is identified by (programme, academic year, batch,
    # version) — "MCA, 2026-2028, v1". Batches admitted earlier stay on the
    # version they were admitted under, forever.
    #
    # Optional at CREATE so the Dean can start sketching immediately, but BOTH
    # are required to submit (governance.submit_for_approval): an approved
    # curriculum is immutable, so "which batch does this govern?" cannot be
    # answered after the fact.
    academic_year:    Optional[str] = Field(default=None, max_length=9)   # '2026-2028'
    regulation_year:  Optional[int] = Field(default=None, ge=1900, le=2200)
    effective_from_batch_id: Optional[UUID] = None
    outcomes:         list[ProgramOutcomeCreate] = []
    courses:          list[CourseCreate] = []


class ProgramUpdate(BaseModel):
    title:            Optional[str] = None
    degree_type:      Optional[str] = None
    department:       Optional[str] = None
    duration_years:   Optional[int] = Field(default=None, ge=1)
    total_credits:    Optional[int] = Field(default=None, ge=1)
    acad_program_id:  Optional[UUID] = None
    ai_instructions:  Optional[str] = None
    academic_year:    Optional[str] = Field(default=None, max_length=9)
    regulation_year:  Optional[int] = Field(default=None, ge=1900, le=2200)
    effective_from_batch_id: Optional[UUID] = None


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
    ai_instructions:     Optional[str]
    # Phase A — governance trail. submitted_* is the Dean handing over (a one-way
    # act); approved_*/locked_* is the Board freezing it, permanently.
    submitted_by_user_id: Optional[UUID] = None
    submitted_at:        Optional[datetime] = None
    approved_by_user_id: Optional[UUID]
    approved_at:         Optional[datetime]
    locked_by_user_id:   Optional[UUID] = None
    locked_at:           Optional[datetime] = None
    review_comment:      Optional[str] = None
    published_by_user_id: Optional[UUID] = None
    published_at:        Optional[datetime] = None
    # Set automatically by the first syllabus generation — the structure the
    # official syllabus was written against. Not a freeze: the Board keeps
    # editing until it approves.
    structure_finalized_at: Optional[datetime] = None
    academic_year:       Optional[str] = None
    regulation_year:     Optional[int] = None
    effective_from_batch_id: Optional[UUID] = None
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


class PublishRequest(BaseModel):
    comment: Optional[str] = None


# RejectRequest is gone. The Board never rejects a curriculum and never returns
# it to the Dean — it enhances the curriculum itself and approves. There is no
# transition this payload could carry.


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
        description="Optional one-time guidance for this generation run.",
    )
    ai_instructions: Optional[str] = Field(
        default=None,
        description="Persisted curriculum instructions stored on the program.",
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
    severity: str   # "ERROR" | "WARNING" | "INFO"


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
