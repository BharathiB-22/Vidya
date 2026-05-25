"""
M08 Exam Setter — Pydantic schemas.

Naming convention:
  *Create  — request body for resource creation
  *Update  — request body for partial update
  *Request — request body for workflow actions
  *Response — response model
  *ListResponse — paginated list wrapper
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Shared sub-schemas
# ---------------------------------------------------------------------------

class QuestionFormatConfig(BaseModel):
    """How many questions of each type to generate."""
    mcq_count:     int = Field(default=0, ge=0)
    short_count:   int = Field(default=0, ge=0)
    long_count:    int = Field(default=0, ge=0)
    problem_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def at_least_one(self) -> "QuestionFormatConfig":
        total = self.mcq_count + self.short_count + self.long_count + self.problem_count
        if total == 0:
            raise ValueError("At least one question format must have count > 0.")
        return self


class BloomsDistribution(BaseModel):
    """Requested or actual Bloom's level distribution (percentages, must sum to 100)."""
    remember:   float = Field(default=0.0, ge=0.0, le=100.0)
    understand: float = Field(default=0.0, ge=0.0, le=100.0)
    apply:      float = Field(default=0.0, ge=0.0, le=100.0)
    analyse:    float = Field(default=0.0, ge=0.0, le=100.0)
    evaluate:   float = Field(default=0.0, ge=0.0, le=100.0)
    create:     float = Field(default=0.0, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def must_sum_to_100(self) -> "BloomsDistribution":
        total = (
            self.remember + self.understand + self.apply
            + self.analyse + self.evaluate + self.create
        )
        if abs(total - 100.0) > 1.0:
            raise ValueError(f"Bloom's distribution must sum to 100 (got {total:.1f}).")
        return self


# ---------------------------------------------------------------------------
# ExamPaper schemas
# ---------------------------------------------------------------------------

class ExamPaperCreate(BaseModel):
    course_id:            UUID
    title:                str = Field(..., min_length=3, max_length=300)
    exam_type:            str = Field(default="END_SEM")
    total_marks:          int = Field(..., gt=0, le=500)
    duration_mins:        int = Field(..., gt=0, le=600)
    units_included:       list[int] = Field(..., min_length=1)
    question_format:      QuestionFormatConfig
    requested_dist:       BloomsDistribution
    special_instructions: str | None = None


class ExamPaperResponse(BaseModel):
    id:                   UUID
    course_id:            UUID
    created_by:           UUID
    title:                str
    exam_type:            str
    total_marks:          int
    duration_mins:        int
    units_included:       list[Any]
    question_format:      dict[str, Any]
    requested_dist:       dict[str, Any]
    actual_dist:          dict[str, Any] | None
    special_instructions: str | None
    ai_model:             str | None
    generation_job_id:    UUID | None
    status:               str
    failure_reason:       str | None
    submitted_at:         datetime | None
    approved_by:          UUID | None
    approved_at:          datetime | None
    board_comment:        str | None
    sealed_at:            datetime | None
    release_at:           datetime | None
    released_at:          datetime | None
    created_at:           datetime
    updated_at:           datetime | None

    model_config = {"from_attributes": True}


class ExamPaperListResponse(BaseModel):
    items:  list[ExamPaperResponse]
    total:  int
    offset: int
    limit:  int


# ---------------------------------------------------------------------------
# ExamQuestion schemas
# ---------------------------------------------------------------------------

class MCQOption(BaseModel):
    label: str  # "A", "B", "C", "D"
    text:  str


class MarkingCriterion(BaseModel):
    criterion:   str
    marks:       float
    description: str


class ExamQuestionResponse(BaseModel):
    id:             UUID
    exam_paper_id:  UUID
    unit_number:    int
    co_code:        str | None
    bloom_level:    str
    question_type:  str
    question_text:  str
    options:        list[Any] | None      # MCQ options (no correct_option exposed here)
    marks:          float
    set_membership: list[str]
    ai_generated:   bool
    is_edited:      bool
    created_at:     datetime
    updated_at:     datetime | None
    # model_answer and correct_option exposed only in answers export (role-gated)

    model_config = {"from_attributes": True}


class ExamQuestionWithAnswerResponse(ExamQuestionResponse):
    """Includes model answer — only for faculty/board/admin post-release export."""
    model_answer:   str | None
    correct_option: str | None
    marking_scheme: list[Any] | None


class ExamQuestionUpdate(BaseModel):
    question_text:   str | None = None
    options:         list[MCQOption] | None = None
    correct_option:  str | None = None
    marks:           float | None = Field(default=None, gt=0)
    model_answer:    str | None = None
    marking_scheme:  list[MarkingCriterion] | None = None
    set_membership:  list[str] | None = None
    bloom_level:     str | None = None


# ---------------------------------------------------------------------------
# Bloom's compliance report schema
# ---------------------------------------------------------------------------

class BloomsViolation(BaseModel):
    level:         str
    requested_pct: float
    actual_pct:    float
    delta_pct:     float


class BloomsComplianceResponse(BaseModel):
    id:             UUID
    exam_paper_id:  UUID
    requested_dist: dict[str, Any]
    actual_dist:    dict[str, Any]
    compliance_ok:  bool
    violations:     list[Any]
    generated_at:   datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Workflow action schemas
# ---------------------------------------------------------------------------

class BoardDecisionRequest(BaseModel):
    approved:      bool
    board_comment: str | None = None

    @model_validator(mode="after")
    def comment_required_on_return(self) -> "BoardDecisionRequest":
        if not self.approved and not self.board_comment:
            raise ValueError("board_comment is required when returning a paper.")
        return self


class SealRequest(BaseModel):
    release_at: datetime = Field(
        ...,
        description="UTC datetime when the paper should be auto-released. Must be in the future.",
    )

    @model_validator(mode="after")
    def must_be_future(self) -> "SealRequest":
        from datetime import timezone
        now = datetime.now(timezone.utc)
        # Ensure timezone-aware comparison
        ra = self.release_at
        if ra.tzinfo is None:
            from datetime import timezone
            ra = ra.replace(tzinfo=timezone.utc)
        if ra <= now:
            raise ValueError("release_at must be in the future.")
        return self


# ---------------------------------------------------------------------------
# Job status polling
# ---------------------------------------------------------------------------

class JobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    result: dict[str, Any] | None = None
