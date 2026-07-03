from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.m03_course_kit.models import (
    AssignmentType,
    BloomLevel,
    ComplexityLevel,
    CourseKitStatus,
)


# ---------------------------------------------------------------------------
# Embedded JSONB sub-models
# ---------------------------------------------------------------------------

_VALID_SLIDE_TYPES = {
    # Original types
    "TITLE", "CONCEPT", "DEFINITION", "EXAMPLE",
    "CODE", "DIAGRAM", "ACTIVITY", "SUMMARY", "QUIZ",
    # Enhanced instructional types (no schema change — stored in JSONB content field)
    "OBJECTIVES", "WORKED_EXAMPLE", "COMMON_MISTAKES", "TOPIC_SUMMARY",
}


class SlideContent(BaseModel):
    """Structure stored in KitSlide.content JSONB.

    All fields are optional so that old kits (without the richer fields) remain
    fully readable.  New AI-generated kits will populate all fields.
    """
    slide_type:         Optional[str]  = Field(default=None, description="TITLE|CONCEPT|DEFINITION|EXAMPLE|CODE|DIAGRAM|ACTIVITY|SUMMARY|QUIZ")
    bullets:            list[str]      = Field(default_factory=list)
    key_concepts:       list[str]      = Field(default_factory=list)
    definitions:        list[str]      = Field(default_factory=list)
    examples:           list[str]      = Field(default_factory=list)
    code_snippet:       Optional[str]  = None
    diagram_prompt:     Optional[str]  = None
    image_hint:         Optional[str]  = None   # kept for backward compat
    classroom_activity: Optional[str]  = None
    student_summary:    Optional[str]  = None
    teaching_notes:     Optional[str]  = None   # faculty-only guidance


class RubricCriterion(BaseModel):
    """One row in KitAssignment.rubric JSONB."""
    criterion:   str = Field(..., min_length=2)
    description: str = Field(..., min_length=5)
    max_marks:   int = Field(..., ge=1)


class TeachingPlanWeek(BaseModel):
    """One week entry in CourseKit.teaching_plan JSONB."""
    week:          int            = Field(..., ge=1)
    topic:         str            = Field(..., min_length=2)
    objectives:    list[str]      = Field(default_factory=list)
    activities:    list[str]      = Field(default_factory=list)
    hours:         int            = Field(..., ge=1)
    co_references: list[str]      = Field(default_factory=list)


class LessonPlanSession(BaseModel):
    """One class session in CourseKit.lesson_plans JSONB."""
    session:          int           = Field(..., ge=1)
    week:             int           = Field(..., ge=1)
    duration_minutes: int           = Field(default=60, ge=30)
    topic:            str           = Field(..., min_length=2)
    objectives:       list[str]     = Field(default_factory=list)
    opening_activity: Optional[str] = None
    main_content:     str           = Field(default="")
    closing_activity: Optional[str] = None
    materials_needed: list[str]     = Field(default_factory=list)
    bloom_levels:     list[str]     = Field(default_factory=list)
    co_references:    list[str]     = Field(default_factory=list)


class ResourceItem(BaseModel):
    """One teaching resource in CourseKit.resources JSONB."""
    title:         str           = Field(..., min_length=2)
    resource_type: str           = Field(..., min_length=2)   # "video","article","book_chapter","website","tool"
    url:           Optional[str] = None
    description:   Optional[str] = None


# ---------------------------------------------------------------------------
# KitSlide schemas
# ---------------------------------------------------------------------------

class KitSlideCreate(BaseModel):
    slide_number:  int                   = Field(..., ge=1)
    title:         str                   = Field(..., min_length=2)
    content:       SlideContent          = Field(default_factory=SlideContent)
    speaker_notes: Optional[str]         = None
    bloom_level:   Optional[BloomLevel]  = None
    co_reference:  Optional[str]         = None


class KitSlideUpdate(BaseModel):
    title:         Optional[str]         = Field(default=None, min_length=2)
    content:       Optional[SlideContent] = None
    speaker_notes: Optional[str]         = None
    bloom_level:   Optional[BloomLevel]  = None
    co_reference:  Optional[str]         = None


class KitSlideResponse(BaseModel):
    """Full response — speaker_notes set to None by router for DEAN role."""
    model_config = {"from_attributes": True}

    id:            UUID
    kit_id:        UUID
    slide_number:  int
    title:         str
    content:       dict[str, Any]
    speaker_notes: Optional[str]
    bloom_level:   Optional[BloomLevel]
    co_reference:  Optional[str]
    created_at:    datetime
    updated_at:    Optional[datetime]


class KitSlideReorder(BaseModel):
    """Maps slide_id → new slide_number for a batch reorder."""
    order: list[tuple[UUID, int]] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# KitAssignment schemas
# ---------------------------------------------------------------------------

class KitAssignmentCreate(BaseModel):
    assignment_number:     int                    = Field(..., ge=1)
    title:                 str                    = Field(..., min_length=3)
    assignment_type:       AssignmentType         = AssignmentType.CLASSWORK
    question_text:         str                    = Field(..., min_length=10)
    # None -> inherit the parent CourseKit's complexity_level (service layer).
    complexity_level:      Optional[ComplexityLevel] = None
    current_events_toggle: bool                   = False
    model_answer:          Optional[str]          = None
    rubric:                list[RubricCriterion]  = Field(default_factory=list)
    bloom_level:           Optional[BloomLevel]   = None
    co_reference:          Optional[str]          = None


class KitAssignmentUpdate(BaseModel):
    title:                 Optional[str]                  = Field(default=None, min_length=3)
    assignment_type:       Optional[AssignmentType]       = None
    question_text:         Optional[str]                  = Field(default=None, min_length=10)
    complexity_level:      Optional[ComplexityLevel]      = None
    current_events_toggle: Optional[bool]                 = None
    model_answer:          Optional[str]                  = None
    rubric:                Optional[list[RubricCriterion]] = None
    bloom_level:           Optional[BloomLevel]           = None
    co_reference:          Optional[str]                  = None


class KitAssignmentResponse(BaseModel):
    """Full response including model_answer.
    Router sets model_answer=None for DEAN role (faculty/admin only field).
    """
    model_config = {"from_attributes": True}

    id:                    UUID
    kit_id:                UUID
    assignment_number:     int
    title:                 str
    assignment_type:       AssignmentType
    question_text:         str
    complexity_level:      ComplexityLevel
    current_events_toggle: bool
    model_answer:          Optional[str]         # None when redacted for DEAN
    rubric:                list[dict[str, Any]]
    bloom_level:           Optional[BloomLevel]
    co_reference:          Optional[str]
    created_at:            datetime
    updated_at:            Optional[datetime]


# ---------------------------------------------------------------------------
# CourseKit schemas
# ---------------------------------------------------------------------------

class CourseKitCreate(BaseModel):
    syllabus_id:         UUID
    unit_number:         int             = Field(..., ge=1)
    # None -> service derives UG/PG from the program's actual degree type.
    complexity_level:    Optional[ComplexityLevel] = None
    tone:                Optional[str]   = None
    custom_instructions: Optional[str]  = None


class CourseKitUpdate(BaseModel):
    complexity_level:    Optional[ComplexityLevel] = None
    tone:                Optional[str]             = None
    custom_instructions: Optional[str]             = None


class CourseKitResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:                  UUID
    syllabus_id:         UUID
    unit_number:         int
    version:             int
    parent_version_id:   Optional[UUID]
    status:              CourseKitStatus
    complexity_level:    ComplexityLevel
    tone:                Optional[str]
    custom_instructions: Optional[str]
    ai_model:            Optional[str]
    created_by_user_id:  UUID
    published_by_user_id: Optional[UUID]
    published_at:        Optional[datetime]
    created_at:          datetime
    updated_at:          Optional[datetime]


class CourseKitDetail(CourseKitResponse):
    """Full kit with all child entities + JSONB plan fields nested."""
    teaching_plan: list[dict[str, Any]]
    lesson_plans:  list[dict[str, Any]]
    resources:     list[dict[str, Any]]
    slides:        list[KitSlideResponse]
    assignments:   list[KitAssignmentResponse]

    course_title: Optional[str] = None
    course_code:  Optional[str] = None
    program_name: Optional[str] = None
    semester:     Optional[int] = None


class CourseKitListItem(CourseKitResponse):
    """List-row shape enriched with course/program/semester (resolved from
    syllabus_id -> Syllabus.course_id -> Course.program_id), mirroring the
    Syllabus module's SyllabusListItem pattern."""
    course_title: Optional[str] = None
    course_code:  Optional[str] = None
    program_name: Optional[str] = None
    semester:     Optional[int] = None


class CourseKitListResponse(BaseModel):
    total:     int
    page:      int
    page_size: int
    items:     list[CourseKitListItem]


class CourseKitStatusResponse(BaseModel):
    """Returned by every state-transition endpoint."""
    model_config = {"from_attributes": True}

    id:         UUID
    version:    int
    status:     CourseKitStatus
    updated_at: Optional[datetime]


class CourseKitVersionResponse(BaseModel):
    """Lightweight row for version history list."""
    model_config = {"from_attributes": True}

    id:                UUID
    version:           int
    parent_version_id: Optional[UUID]
    status:            CourseKitStatus
    created_by_user_id: UUID
    published_at:      Optional[datetime]
    created_at:        datetime


# ---------------------------------------------------------------------------
# Action / state-transition request schemas
# ---------------------------------------------------------------------------

class GenerateKitRequest(BaseModel):
    custom_instructions: Optional[str] = Field(
        default=None,
        description="Optional faculty guidance for the AI generator.",
    )
    complexity_level: Optional[ComplexityLevel] = Field(
        default=None,
        description="Override kit complexity level before generating.",
    )
    tone: Optional[str] = Field(
        default=None,
        description="Tone hint for generated content (e.g. 'formal', 'conversational').",
    )


class KitAIJobResponse(BaseModel):
    job_id:     UUID
    kit_id:     UUID
    status:     str = "queued"


class PublishRequest(BaseModel):
    comment: Optional[str] = None


class ArchiveRequest(BaseModel):
    reason: Optional[str] = None


class ForkRequest(BaseModel):
    """Fork a PUBLISHED or ARCHIVED kit into a new DRAFT."""
    change_note: Optional[str] = None


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

class KitExportRequest(BaseModel):
    format: str = Field(
        default="pptx",
        description=(
            "Export format: 'pptx' (full deck with speaker notes, faculty only fields),"
            " 'pdf' (faculty slide deck, role-aware), or"
            " 'handout' (student PDF — sanitized, no answer keys / notes / rubrics)."
        ),
    )


class KitExportJobResponse(BaseModel):
    job_id:  UUID
    kit_id:  UUID
    format:  str


# ---------------------------------------------------------------------------
# Faculty-uploaded resources (PDF/PPT/DOCX/notes) — kit_id is a path param,
# so requests only carry file metadata; entity_type/entity_id are filled in
# server-side before delegating to the generic storage module.
# ---------------------------------------------------------------------------

class KitResourceUploadUrlRequest(BaseModel):
    original_filename: str = Field(..., min_length=1)
    content_type:      str
    size_bytes:        int = Field(..., ge=1)


class KitResourceConfirmRequest(BaseModel):
    object_key:        str
    original_filename: str = Field(..., min_length=1)
    content_type:      str
    size_bytes:        int = Field(..., ge=1)
    status:  str = "queued"
