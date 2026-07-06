"""
M04 Assignments — Pydantic schemas.

Request / response models for the HTTP layer only.
Business logic lives in service.py; DB logic in repository.py.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

_ASSIGNMENT_TYPES = ("ESSAY", "CASE_STUDY", "REPORT", "HOMEWORK", "OTHER")


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------

class AssignmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    instructions: str | None = None
    assignment_type: str = "HOMEWORK"
    syllabus_id: UUID | None = None
    max_marks: float = Field(gt=0)
    weightage_percent: float | None = Field(default=None, ge=0, le=100)
    due_date: datetime | None = None
    allow_late: bool = True
    late_penalty_percent: float | None = Field(default=None, ge=0, le=100)
    max_attempts: int = Field(default=1, ge=1, le=10)
    allowed_file_types: list[str] = Field(default_factory=list)

    @field_validator("assignment_type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in _ASSIGNMENT_TYPES:
            raise ValueError(f"assignment_type must be one of {_ASSIGNMENT_TYPES}")
        return v


class AssignmentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    instructions: str | None = None
    assignment_type: str | None = None
    max_marks: float | None = Field(default=None, gt=0)
    weightage_percent: float | None = Field(default=None, ge=0, le=100)
    due_date: datetime | None = None
    allow_late: bool | None = None
    late_penalty_percent: float | None = Field(default=None, ge=0, le=100)
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    allowed_file_types: list[str] | None = None


class AssignmentResponse(BaseModel):
    id: UUID
    title: str
    description: str | None
    instructions: str | None
    assignment_type: str
    syllabus_id: UUID | None
    max_marks: float
    weightage_percent: float | None
    due_date: datetime | None
    allow_late: bool
    late_penalty_percent: float | None
    max_attempts: int
    allowed_file_types: list[str]
    status: str
    created_by_user_id: UUID
    published_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime | None
    # Enriched from syllabi -> courses join (populated on detail endpoints only)
    course_title: str | None = None
    course_code: str | None = None

    model_config = {"from_attributes": True}


class AssignmentListResponse(BaseModel):
    items: list[AssignmentResponse]
    total: int
    offset: int
    limit: int


class AssignmentStatistics(BaseModel):
    total_students: int
    submitted_count: int
    graded_count: int
    late_count: int
    average_marks: float | None


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------

class SubmissionCreate(BaseModel):
    content_text: str | None = None
    # For file uploads: client uses the generic storage presigned-upload flow,
    # then passes the returned object_key here.
    content_url: str | None = None


class SubmissionResponse(BaseModel):
    id: UUID
    assignment_id: UUID
    student_user_id: UUID
    attempt_number: int
    content_url: str | None
    # content_text omitted from list view — too large; included in detail below
    submitted_at: datetime
    is_late: bool
    status: str
    marks_obtained: float | None
    feedback: str | None
    graded_by_user_id: UUID | None
    graded_at: datetime | None
    returned_at: datetime | None
    # Enriched (faculty submissions list only)
    student_name: str | None = None

    model_config = {"from_attributes": True}


class SubmissionDetailResponse(SubmissionResponse):
    content_text: str | None

    model_config = {"from_attributes": True}


class SubmissionListResponse(BaseModel):
    items: list[SubmissionResponse]
    total: int
    offset: int
    limit: int


class GradeSubmissionRequest(BaseModel):
    marks_obtained: float = Field(ge=0)
    feedback: str | None = None
