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
# Assignment questions
# ---------------------------------------------------------------------------

class AssignmentQuestion(BaseModel):
    """One question in the assignment's question builder.

    `marks` is per-question; across the whole assignment they sum to max_marks
    (checked in the service, where the max is known). Kept as a plain value
    object — the questions live inline on the assignment (JSONB), not as rows.
    """
    question_number: int = Field(ge=1)
    question_text:   str = Field(min_length=1)
    marks:           float = Field(gt=0)
    notes:           str | None = None


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
    # The evaluator(s) this coursework should route to. Each student submission
    # becomes one work item against these, round-robin, through the existing M09.6
    # engine. Empty = nobody nominated; the department allocates by hand as before.
    evaluator_user_ids: list[UUID] = Field(default_factory=list)
    # The question builder. Empty = no structured questions (a question paper may
    # be uploaded instead, or none at all). When non-empty, marks must sum to
    # max_marks — enforced in the service.
    questions: list[AssignmentQuestion] = Field(default_factory=list)
    # S3 object key of an uploaded question paper (.pdf/.docx), the fallback when
    # no structured questions are entered.
    question_paper_url: str | None = None

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
    evaluator_user_ids: list[UUID] | None = None
    questions: list[AssignmentQuestion] | None = None
    question_paper_url: str | None = None


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
    evaluator_user_ids: list[UUID] = Field(default_factory=list)
    questions: list[AssignmentQuestion] = Field(default_factory=list)
    question_paper_url: str | None = None
    status: str
    created_by_user_id: UUID
    published_at: datetime | None
    closed_at: datetime | None
    submitted_at: datetime | None = None
    submitted_by_user_id: UUID | None = None
    finalized_at: datetime | None = None
    finalized_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime | None
    # Enriched from syllabi -> courses join (populated on detail endpoints only)
    course_title: str | None = None
    course_code: str | None = None

    @field_validator("evaluator_user_ids", "questions", mode="before")
    @classmethod
    def _null_is_empty(cls, v: object) -> object:
        # These columns are nullable — "none set" reads as [] to every caller
        # rather than making each one handle null.
        return [] if v is None else v

    model_config = {"from_attributes": True}


class EligibleEvaluator(BaseModel):
    """A user who may be allocated coursework to evaluate."""
    id:        UUID
    full_name: str | None = None
    email:     str | None = None
    role:      str


class MyCourseworkEvaluation(BaseModel):
    """One coursework submission allocated to the calling evaluator.

    A read over the M09.6 ledger joined back to the coursework it belongs to —
    enough for the evaluator to find the work and open it. No allocation logic
    lives here; this only answers "what is on my desk, and where is it".
    """
    submission_id:   UUID
    assignment_id:   UUID
    assignment_title: str
    course_title:    str | None = None
    course_code:     str | None = None
    student_name:    str | None = None
    attempt_number:  int
    submitted_at:    datetime
    is_late:         bool
    submission_status: str
    assignment_status: str
    max_marks:       float
    marks_obtained:  float | None = None
    due_at:          datetime | None = None
    allocation_status: str


class AssignEvaluatorRequest(BaseModel):
    """Allocate one student submission to one evaluator.

    The allocation itself is recorded by the M09.6 assignment engine, which is the
    single ledger for evaluation work; this is just the coursework-facing way in.
    """
    evaluator_user_id: UUID
    due_at:            datetime | None = None
    notes:             str | None = None


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
    # Who the M09.6 engine currently has evaluating this submission; None until
    # the department allocates one. Read from that ledger, never stored here.
    evaluator_user_id: UUID | None = None
    evaluator_name: str | None = None

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
