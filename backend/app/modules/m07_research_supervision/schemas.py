"""
M07 Research Supervision — Pydantic request/response schemas.

Naming convention:
  *Create   — POST body for creating a resource
  *Update   — PATCH/PUT body for editing
  *Response — serialised response (single item)
  *ListResponse — paginated list wrapper
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

class ResearchQuestion(BaseModel):
    question: str = Field(..., min_length=1)


class GuideUserResponse(BaseModel):
    id: UUID
    full_name: str
    email: str
    identifier: str | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# ResearchProblem schemas
# ---------------------------------------------------------------------------

class ProblemCreate(BaseModel):
    """Student submits a research problem proposal."""
    guide_user_id:      UUID
    title:              str = Field(..., min_length=5, max_length=300)
    abstract:           str | None = Field(None, max_length=5000)
    research_questions: list[ResearchQuestion] = Field(..., min_length=1, max_length=5)

    @field_validator("research_questions")
    @classmethod
    def at_least_one_question(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one research question is required.")
        return v


class AIGeneratedProblemCreate(BaseModel):
    """Guide creates an AI-generated problem to offer to a student."""
    guide_user_id: UUID
    research_area: str = Field(..., min_length=5, max_length=500)
    num_problems:  int = Field(default=3, ge=1, le=5)


class GuideDecisionRequest(BaseModel):
    """Guide decides on a student proposal. HUMAN GATE 1."""
    decision:    str  # "ACCEPT" | "REVISE" | "REJECT"
    guide_note:  str | None = Field(None, max_length=2000)

    @field_validator("decision")
    @classmethod
    def valid_decision(cls, v: str) -> str:
        allowed = {"ACCEPT", "REVISE", "REJECT"}
        if v not in allowed:
            raise ValueError(f"decision must be one of {allowed}")
        return v


class ProblemResponse(BaseModel):
    id:                 UUID
    guide_user_id:      UUID
    student_user_id:    UUID | None
    title:              str
    abstract:           str | None
    research_questions: list[dict]
    source:             str
    novelty_score:      float | None
    feasibility_score:  float | None
    clarity_score:      float | None
    ai_recommendation:  str | None
    ai_reasoning:       str | None
    ai_model:           str | None
    eval_job_id:        UUID | None
    status:             str
    guide_decision:     str | None
    guide_note:         str | None
    decided_at:         datetime | None
    created_at:         datetime
    updated_at:         datetime | None

    model_config = {"from_attributes": True}


class ProblemListResponse(BaseModel):
    items:  list[ProblemResponse]
    total:  int
    offset: int
    limit:  int


# ---------------------------------------------------------------------------
# AI-generated problem output (not stored directly — passed to guide)
# ---------------------------------------------------------------------------

class GeneratedProblemItem(BaseModel):
    title:              str
    abstract:           str
    research_questions: list[str]
    reasoning:          str


class GeneratedProblemsResponse(BaseModel):
    problems: list[GeneratedProblemItem]
    ai_model: str


# ---------------------------------------------------------------------------
# ResearchDocument schemas
# ---------------------------------------------------------------------------

class DocumentSubmit(BaseModel):
    """Student submits a research document (file upload handled separately)."""
    research_problem_id: UUID
    file_url:            str | None = None   # S3 key; set after presigned upload
    file_name:           str | None = Field(None, max_length=255)


class DocumentFileUpdate(BaseModel):
    """Set file_url after upload completes."""
    file_url:  str
    file_name: str | None = None


class GuideDocumentReviewRequest(BaseModel):
    """Guide approves or requests revision on a document. HUMAN GATE 2."""
    decision:      str  # "APPROVE" | "REQUEST_REVISION"
    guide_comment: str | None = Field(None, max_length=3000)

    @field_validator("decision")
    @classmethod
    def valid_decision(cls, v: str) -> str:
        allowed = {"APPROVE", "REQUEST_REVISION"}
        if v not in allowed:
            raise ValueError(f"decision must be one of {allowed}")
        return v


class DocumentResponse(BaseModel):
    id:                  UUID
    research_problem_id: UUID
    student_user_id:     UUID
    version:             int
    file_url:            str | None
    file_name:           str | None
    plagiarism_score:    float | None
    ai_content_score:    float | None
    format_score:        float | None
    clarity_score:       float | None
    evaluation_report:   dict | None
    ai_model:            str | None
    eval_job_id:         UUID | None
    status:              str
    guide_comment:       str | None
    guide_reviewed_at:   datetime | None
    submitted_at:        datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items:  list[DocumentResponse]
    total:  int
    offset: int
    limit:  int


# ---------------------------------------------------------------------------
# VivaSession schemas
# ---------------------------------------------------------------------------

class VivaScheduleRequest(BaseModel):
    """Guide schedules a viva session."""
    research_problem_id: UUID
    document_id:         UUID
    student_user_id:     UUID | None = None   # derived from approved document if omitted
    scheduled_at:        datetime | None = None
    session_ttl_hours:   int = Field(default=72, ge=1, le=720)


class VivaConsentRequest(BaseModel):
    """Student records explicit consent before viva session starts. DPDP."""
    consent: bool = True


class VivaResponseSubmit(BaseModel):
    """Student submits one recorded response during viva."""
    question_id:   str
    response_text: str = Field(..., min_length=1)
    start_ms:      int | None = None
    end_ms:        int | None = None


class VivaOfflineResponse(BaseModel):
    """One Q&A pair submitted by the guide during an offline viva."""
    question_id:   str = Field(..., min_length=1)
    response_text: str = Field(..., min_length=1, max_length=10000)


class VivaConductRequest(BaseModel):
    """Guide conducts an offline viva by submitting all Q&A responses at once."""
    responses: list[VivaOfflineResponse] = Field(..., min_length=1)


class VivaCompleteRequest(BaseModel):
    """Student marks session as complete and provides video upload URL."""
    video_url: str


class QuestionScoreOverride(BaseModel):
    question_id:    str
    score_override: float | None = Field(None, ge=0.0, le=10.0)
    comment:        str | None = Field(None, max_length=1000)


class VivaRatifyRequest(BaseModel):
    """Guide ratifies viva evaluation. HUMAN GATE 3. AI advises, human decides."""
    overall_guide_score: float = Field(..., ge=0.0, le=10.0)
    ratification_note:   str | None = Field(None, max_length=2000)


class VivaSessionResponse(BaseModel):
    id:                  UUID
    research_problem_id: UUID
    document_id:         UUID
    student_user_id:     UUID
    guide_user_id:       UUID
    session_token:       str
    ai_questions:        list[dict]
    ai_responses:        list[dict]
    video_url:           str | None
    transcript:          str | None
    ai_evaluation:       dict | None   # {per_question, overall_score, ai_model}
    overall_ai_score:    float | None
    guide_evaluation:    dict | None    # {overall_guide_score, ratification_note}
    overall_guide_score: float | None
    consent_recorded:    bool
    ai_model:            str | None
    eval_job_id:         UUID | None
    scheduled_at:        datetime | None
    expires_at:          datetime | None
    completed_at:        datetime | None
    ratified_at:         datetime | None
    status:              str

    model_config = {"from_attributes": True}


class VivaListResponse(BaseModel):
    items:  list[VivaSessionResponse]
    total:  int
    offset: int
    limit:  int


# ---------------------------------------------------------------------------
# Job status (shared pattern with M06)
# ---------------------------------------------------------------------------

class JobStatusResponse(BaseModel):
    job_id:       UUID
    status:       str
    result:       Any | None
    error:        str | None
    created_at:   datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}
