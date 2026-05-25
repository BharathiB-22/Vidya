"""
M06 Labs & Assignment Evaluator — Pydantic schemas.

Request / response models for the HTTP layer only.
Business logic lives in service.py; DB logic in repository.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Rubric criterion
# ---------------------------------------------------------------------------

class RubricCriterion(BaseModel):
    criterion_id: str
    name: str
    description: str = ""
    max_marks: int = Field(ge=1)
    weight: float = Field(ge=0.0, le=1.0)


class TestCase(BaseModel):
    id: str
    name: str
    stdin: str = ""
    expected_stdout: str
    is_hidden: bool = False
    points: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------

class AssignmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    submission_type: str = "WRITTEN"          # WRITTEN | CODE
    language: str | None = None               # e.g. "python" — CODE only
    rubric: list[RubricCriterion] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)
    syllabus_id: UUID | None = None
    kit_assignment_id: UUID | None = None
    deadline: datetime | None = None
    ai_not_permitted: bool = True
    allow_late: bool = False
    plagiarism_threshold: float = Field(default=0.85, ge=0.0, le=1.0)

    @field_validator("rubric")
    @classmethod
    def rubric_weights_sum(cls, v: list[RubricCriterion]) -> list[RubricCriterion]:
        if v:
            total = sum(c.weight for c in v)
            if abs(total - 1.0) > 0.01:
                raise ValueError(f"Rubric weights must sum to 1.0; got {total:.3f}")
        return v

    @field_validator("submission_type")
    @classmethod
    def valid_submission_type(cls, v: str) -> str:
        if v not in ("WRITTEN", "CODE"):
            raise ValueError("submission_type must be WRITTEN or CODE")
        return v


class AssignmentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    rubric: list[RubricCriterion] | None = None
    test_cases: list[TestCase] | None = None
    deadline: datetime | None = None
    ai_not_permitted: bool | None = None
    allow_late: bool | None = None
    plagiarism_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    language: str | None = None


class AssignmentResponse(BaseModel):
    id: UUID
    title: str
    description: str | None
    submission_type: str
    language: str | None
    rubric: list[dict]
    test_cases: list[dict]          # hidden test cases stripped for students
    max_marks: int | None
    deadline: datetime | None
    ai_not_permitted: bool
    allow_late: bool
    plagiarism_threshold: float
    status: str
    syllabus_id: UUID | None
    kit_assignment_id: UUID | None
    created_by_user_id: UUID
    published_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class AssignmentListResponse(BaseModel):
    items: list[AssignmentResponse]
    total: int
    offset: int
    limit: int


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------

class SubmissionCreate(BaseModel):
    content_text: str | None = None    # inline code or text
    # For file uploads: client uses storage presigned URL, then passes the object key here
    content_url: str | None = None

    @field_validator("content_text", "content_url", mode="before")
    @classmethod
    def at_least_one(cls, v: Any, info: Any) -> Any:
        return v


class SubmissionResponse(BaseModel):
    id: UUID
    assignment_id: UUID
    student_user_id: UUID
    submission_type: str
    content_url: str | None
    # content_text not returned in list view — too large
    submitted_at: datetime
    is_late: bool
    eval_job_id: UUID | None
    ai_scan_status: str
    status: str
    # Populated for RATIFIED submissions (joined from grade_ledger)
    final_score: float | None = None
    graded_max_marks: int | None = None

    model_config = {"from_attributes": True}


class SubmissionDetailResponse(SubmissionResponse):
    """Full detail including content and evaluation — faculty or own student."""
    content_text: str | None
    ai_scan_result: dict | None
    evaluation: EvaluationResponse | None = None

    model_config = {"from_attributes": True}


class SubmissionListResponse(BaseModel):
    items: list[SubmissionResponse]
    total: int
    offset: int
    limit: int


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

class CriterionScoreUpdate(BaseModel):
    criterion_id: str
    human_score: float = Field(ge=0.0)
    human_note: str | None = None


class ScoresUpdateRequest(BaseModel):
    scores: list[CriterionScoreUpdate]


class EvaluationResponse(BaseModel):
    id: UUID
    submission_id: UUID
    rubric_scores: list[dict]
    overall_ai_score: float | None
    overall_human_score: float | None
    confidence_level: str | None
    test_results: list[dict] | None
    static_analysis: dict | None
    plagiarism_score: float | None
    plagiarism_matches: list[dict] | None
    ai_model: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Review panel (faculty)
# ---------------------------------------------------------------------------

class ReviewPanelResponse(BaseModel):
    submission: SubmissionDetailResponse
    assignment: AssignmentResponse
    grade_entry: GradeLedgerResponse | None = None


# ---------------------------------------------------------------------------
# Ratification
# ---------------------------------------------------------------------------

class RatifyRequest(BaseModel):
    ratification_note: str | None = None


class GradeLedgerResponse(BaseModel):
    id: UUID
    submission_id: UUID
    assignment_id: UUID
    student_user_id: UUID
    ratified_by_user_id: UUID
    final_score: float
    max_marks: int
    ratification_note: str | None
    ratified_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Job status (poll Celery task_jobs)
# ---------------------------------------------------------------------------

class JobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    result: dict | None = None
    error: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
