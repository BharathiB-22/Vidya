from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.m02_syllabus.models import (
    BloomLevel,
    MappingStrength,
    RefSource,
    RefType,
    SyllabusStatus,
)


# ---------------------------------------------------------------------------
# Unit topic item (embedded in SyllabusUnit.topics JSONB)
# ---------------------------------------------------------------------------

class UnitTopicItem(BaseModel):
    title:          str
    description:    Optional[str] = None
    hours_estimate: Optional[int] = Field(default=None, ge=1)


# ---------------------------------------------------------------------------
# Course outcome schemas
# ---------------------------------------------------------------------------

class CourseOutcomeCreate(BaseModel):
    code:          str = Field(..., min_length=1, max_length=20)
    description:   str = Field(..., min_length=10)
    bloom_level:   BloomLevel
    display_order: int = Field(default=0, ge=0)


class CourseOutcomeUpdate(BaseModel):
    description:   Optional[str]       = Field(default=None, min_length=10)
    bloom_level:   Optional[BloomLevel] = None
    display_order: Optional[int]        = Field(default=None, ge=0)


class CourseOutcomeResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:            UUID
    syllabus_id:   UUID
    code:          str
    description:   str
    bloom_level:   BloomLevel
    display_order: int
    created_at:    datetime
    updated_at:    Optional[datetime]


# ---------------------------------------------------------------------------
# CO-PO mapping schemas
# ---------------------------------------------------------------------------

class COPOMappingCreate(BaseModel):
    po_id:            UUID
    mapping_strength: MappingStrength = MappingStrength.MEDIUM
    justification:    Optional[str]   = None


class COPOMappingUpdate(BaseModel):
    mapping_strength: Optional[MappingStrength] = None
    justification:    Optional[str]             = None


class COPOMappingResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:               UUID
    co_id:            UUID
    po_id:            UUID
    mapping_strength: MappingStrength
    justification:    Optional[str]
    created_at:       datetime


class COPOMappingBulkUpdate(BaseModel):
    """Replaces all PO mappings for a single CO in one PUT call."""
    mappings: list[COPOMappingCreate] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# CO-PO matrix response (for display and export)
# ---------------------------------------------------------------------------

class COPOMatrixPOHeader(BaseModel):
    po_id:        UUID
    po_code:      str
    po_description: str


class COPOMatrixCell(BaseModel):
    po_id:            UUID
    po_code:          str
    mapping_strength: Optional[MappingStrength] = None
    justification:    Optional[str]             = None


class COPOMatrixRow(BaseModel):
    co_id:       UUID
    co_code:     str
    description: str
    bloom_level: BloomLevel
    cells:       list[COPOMatrixCell]


class COPOMatrixResponse(BaseModel):
    syllabus_id:      UUID
    course_id:        UUID
    po_headers:       list[COPOMatrixPOHeader]
    rows:             list[COPOMatrixRow]


# ---------------------------------------------------------------------------
# Syllabus unit schemas
# ---------------------------------------------------------------------------

class SyllabusUnitCreate(BaseModel):
    unit_number: int          = Field(..., ge=1)
    title:       str          = Field(..., min_length=3)
    topics:      list[UnitTopicItem] = Field(default_factory=list)
    total_hours: int          = Field(..., ge=1)
    pedagogy:    Optional[str] = None


class SyllabusUnitUpdate(BaseModel):
    title:       Optional[str]              = Field(default=None, min_length=3)
    topics:      Optional[list[UnitTopicItem]] = None
    total_hours: Optional[int]              = Field(default=None, ge=1)
    pedagogy:    Optional[str]              = None


class SyllabusUnitReorder(BaseModel):
    """Maps unit_id → new unit_number for a batch reorder."""
    order: list[tuple[UUID, int]] = Field(..., min_length=1)


class SyllabusUnitResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:           UUID
    syllabus_id:  UUID
    unit_number:  int
    title:        str
    topics:       list[UnitTopicItem]
    total_hours:  int
    pedagogy:     Optional[str]
    bloom_summary: Optional[list[dict]]
    created_at:   datetime
    updated_at:   Optional[datetime]


# ---------------------------------------------------------------------------
# Syllabus reference schemas
# ---------------------------------------------------------------------------

class SyllabusReferenceCreate(BaseModel):
    title:        str              = Field(..., min_length=3)
    authors:      list[str]        = Field(default_factory=list)
    year:         Optional[int]    = Field(default=None, ge=1000, le=2100)
    ref_type:     RefType          = RefType.TEXTBOOK
    source:       RefSource        = RefSource.MANUAL
    doi:          Optional[str]    = None
    isbn:         Optional[str]    = None
    url:          Optional[str]    = None
    publisher:    Optional[str]    = None
    is_confirmed: bool             = True


class SyllabusReferenceUpdate(BaseModel):
    title:        Optional[str]     = Field(default=None, min_length=3)
    authors:      Optional[list[str]] = None
    year:         Optional[int]     = Field(default=None, ge=1000, le=2100)
    ref_type:     Optional[RefType] = None
    doi:          Optional[str]     = None
    isbn:         Optional[str]     = None
    url:          Optional[str]     = None
    publisher:    Optional[str]     = None
    is_confirmed: Optional[bool]    = None


class SyllabusReferenceResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:           UUID
    syllabus_id:  UUID
    title:        str
    authors:      list[str]
    year:         Optional[int]
    ref_type:     RefType
    source:       RefSource
    doi:          Optional[str]
    isbn:         Optional[str]
    url:          Optional[str]
    publisher:    Optional[str]
    is_confirmed: bool
    created_at:   datetime
    updated_at:   Optional[datetime]


# ---------------------------------------------------------------------------
# Reference search schemas (faculty-initiated CrossRef / OpenLibrary search)
# ---------------------------------------------------------------------------

class ReferenceSearchRequest(BaseModel):
    query:    str     = Field(..., min_length=3)
    ref_type: RefType = RefType.TEXTBOOK
    limit:    int     = Field(default=5, ge=1, le=20)


class ReferenceCandidate(BaseModel):
    """Candidate from CrossRef or OpenLibrary — not yet attached to a syllabus."""
    title:     str
    authors:   list[str]
    year:      Optional[int]
    ref_type:  RefType
    source:    RefSource
    doi:       Optional[str] = None
    isbn:      Optional[str] = None
    url:       Optional[str] = None
    publisher: Optional[str] = None


# ---------------------------------------------------------------------------
# Syllabus schemas
# ---------------------------------------------------------------------------

class SyllabusCreate(BaseModel):
    course_id:           UUID
    custom_instructions: Optional[str] = None


class SyllabusUpdate(BaseModel):
    custom_instructions: Optional[str] = None


class SyllabusResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:                  UUID
    course_id:           UUID
    version:             int
    parent_version_id:   Optional[UUID]
    status:              SyllabusStatus
    custom_instructions: Optional[str]
    change_note:         Optional[str]
    ai_model:            Optional[str]
    prompt_hash:         Optional[str]
    created_by_user_id:  UUID
    approved_by_user_id: Optional[UUID]
    approved_at:         Optional[datetime]
    locked_by_user_id:   Optional[UUID]
    locked_at:           Optional[datetime]
    created_at:          datetime
    updated_at:          Optional[datetime]


class SyllabusDetail(SyllabusResponse):
    """Full syllabus with all child entities nested."""
    outcomes:   list[CourseOutcomeResponse]
    units:      list[SyllabusUnitResponse]
    references: list[SyllabusReferenceResponse]


class SyllabusListResponse(BaseModel):
    total:     int
    page:      int
    page_size: int
    items:     list[SyllabusResponse]


class SyllabusVersionResponse(BaseModel):
    """Lightweight row for version history list."""
    model_config = {"from_attributes": True}

    id:                 UUID
    version:            int
    parent_version_id:  Optional[UUID]
    status:             SyllabusStatus
    change_note:        Optional[str]
    created_by_user_id: UUID
    created_at:         datetime


class SyllabusStatusResponse(BaseModel):
    """Returned by every state-transition endpoint."""
    model_config = {"from_attributes": True}

    id:         UUID
    version:    int
    status:     SyllabusStatus
    updated_at: Optional[datetime]


# ---------------------------------------------------------------------------
# Action request schemas (state machine transitions)
# ---------------------------------------------------------------------------

class GenerateSyllabusRequest(BaseModel):
    custom_instructions: Optional[str] = Field(
        default=None,
        description="Optional guidance for the AI generator.",
    )


class SyllabusAIJobResponse(BaseModel):
    job_id:      UUID
    syllabus_id: UUID
    status:      str = "queued"


class SaveVersionRequest(BaseModel):
    change_note: Optional[str] = None


class ForkRequest(BaseModel):
    """Fork any historical syllabus version into a new DRAFT."""
    change_note: Optional[str] = None


class ApproveRequest(BaseModel):
    comment: Optional[str] = None


class RejectRequest(BaseModel):
    """Returns FACULTY_APPROVED back to a new DRAFT version."""
    reason: str = Field(..., min_length=5)


class LockRequest(BaseModel):
    comment: Optional[str] = None


# ---------------------------------------------------------------------------
# Compliance schemas
# ---------------------------------------------------------------------------

class ComplianceViolation(BaseModel):
    code:     str
    message:  str
    severity: str   # "ERROR" | "WARNING"


class ComplianceCheckResponse(BaseModel):
    passed:     bool
    violations: list[ComplianceViolation]


# ---------------------------------------------------------------------------
# Export schemas
# ---------------------------------------------------------------------------

class SyllabusExportJobResponse(BaseModel):
    job_id:      UUID
    syllabus_id: UUID
    format:      str        # "pdf" | "docx" | "json"
    status:      str = "queued"
