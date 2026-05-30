"""
M09 Paper Administration & Scanning — Pydantic schemas.

Identity masking rule:
  ScannedScriptResponse NEVER exposes student_user_id or student_roll_ref
  unless include_identity=True is explicitly requested AND status == BOARD_FINALISED.
  The service layer enforces this; schemas reflect it via Optional fields.

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
# ScriptEvaluation schemas
# ---------------------------------------------------------------------------

class ScriptEvaluationResponse(BaseModel):
    """
    AI suggestion + optional human marks for one question.
    Used in evaluation panel — one row per question in the script.
    Enrichment fields (keyword_hits, rubric_mapping, ai_confidence, page_range)
    are populated after H-36 STEP-04 scoring and exposed to the evaluator.
    """
    id:                  UUID
    script_id:           UUID
    question_id:         UUID
    question_type:       str
    max_marks:           float
    evaluation_round:    str

    ai_suggested_marks:  float | None
    ai_justification:    str | None
    ai_model:            str | None

    # H-36 STEP-04 enrichment — visible to evaluator in the review panel
    keyword_hits:        list[dict] | None = None
    rubric_mapping:      list[dict] | None = None
    ai_confidence:       float | None = None
    page_range:          dict | None = None

    evaluator_marks:     float | None
    evaluator_note:      str | None

    final_marks:         float | None

    created_at:          datetime
    updated_at:          datetime | None

    model_config = {"from_attributes": True}


class EvaluatorMarkUpdate(BaseModel):
    """
    Evaluator enters or updates their mark for a single question.
    Only evaluator_marks and evaluator_note are writable by humans.
    """
    evaluator_marks: float = Field(..., ge=0)
    evaluator_note:  str | None = None


class BulkMarkUpdate(BaseModel):
    """
    Evaluator submits all question marks in a single request.
    Keyed by question_id (UUID string).
    """
    marks: dict[str, EvaluatorMarkUpdate] = Field(
        ...,
        description="Mapping of question_id (str UUID) → mark update."
    )

    @model_validator(mode="after")
    def at_least_one(self) -> "BulkMarkUpdate":
        if not self.marks:
            raise ValueError("marks dict must contain at least one entry.")
        return self


# ---------------------------------------------------------------------------
# ScannedScript schemas
# ---------------------------------------------------------------------------

class ScriptIngestRequest(BaseModel):
    """
    Request body for uploading a new scanned answer script.
    student_user_id / student_roll_ref are provided by Admin/Board (role-gated).
    The API accepts multipart/form-data; this schema covers the JSON fields.
    """
    exam_paper_id:      UUID
    student_user_id:    UUID | None = None
    student_roll_ref:   str | None = None


class ScriptAssignEvaluatorRequest(BaseModel):
    evaluator_id:        UUID
    second_evaluator_id: UUID | None = None


class ScriptSubmitMarksRequest(BaseModel):
    """Gate 1: evaluator submits all marks and triggers status → MARKS_SUBMITTED."""
    marks: dict[str, EvaluatorMarkUpdate] = Field(
        ...,
        description="Mapping of question_id (str UUID) → mark update."
    )
    submission_note: str | None = None

    @model_validator(mode="after")
    def at_least_one(self) -> "ScriptSubmitMarksRequest":
        if not self.marks:
            raise ValueError("marks dict must contain at least one entry.")
        return self


class ScriptFinaliseRequest(BaseModel):
    """Gate 2: Board member finalises marks and writes to exam_score_ledger."""
    finalisation_note: str | None = None


class ScannedScriptResponse(BaseModel):
    """
    Public API response for a scanned script.

    Identity masking: student_user_id and student_roll_ref are returned as None
    unless the script status is BOARD_FINALISED.  The service layer strips these
    fields before returning to any caller — this schema reflects the result.
    """
    id:                  UUID
    exam_paper_id:       UUID
    masked_id:           str

    # Identity — None until BOARD_FINALISED (service enforces this)
    student_user_id:     UUID | None
    student_roll_ref:    str | None

    upload_url:          str | None
    page_count:          int | None

    status:              str
    eval_job_id:         UUID | None
    objective_auto_score: float | None

    evaluator_id:        UUID | None
    second_evaluator_id: UUID | None

    submitted_by:        UUID | None
    submitted_at:        datetime | None

    finalised_by:        UUID | None
    finalised_at:        datetime | None

    # OCR placeholders (null until OCR pipeline implemented)
    ocr_status:          str | None

    created_at:          datetime
    updated_at:          datetime | None

    model_config = {"from_attributes": True}


class ScannedScriptListResponse(BaseModel):
    items:  list[ScannedScriptResponse]
    total:  int
    offset: int
    limit:  int


# ---------------------------------------------------------------------------
# ExamScoreLedger schemas
# ---------------------------------------------------------------------------

class ExamScoreLedgerResponse(BaseModel):
    """
    Board-finalised score record. Only accessible after BOARD_FINALISED.
    Includes student identity (revealed at finalisation time).
    """
    id:                UUID
    script_id:         UUID
    exam_paper_id:     UUID
    student_user_id:   UUID | None
    student_roll_ref:  str | None
    total_marks:       float
    max_marks:         float
    finalised_by:      UUID
    finalisation_note: str | None
    finalised_at:      datetime

    model_config = {"from_attributes": True}


class ExamScoreLedgerListResponse(BaseModel):
    items:  list[ExamScoreLedgerResponse]
    total:  int
    offset: int
    limit:  int


# ---------------------------------------------------------------------------
# Job status polling (shared pattern with M08)
# ---------------------------------------------------------------------------

class JobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    result: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Evaluator review panel (STEP-05)
# ---------------------------------------------------------------------------

class EvaluatorReviewResponse(BaseModel):
    """
    Combined payload for the evaluator review panel.
    Includes the full OCR text (evaluator context) and enriched AI evaluations.
    Identity is always masked (student_user_id / student_roll_ref not included).
    """
    script_id:            UUID
    masked_id:            str
    exam_paper_id:        UUID
    status:               str
    ocr_text:             str | None
    ocr_status:           str | None
    page_count:           int | None
    page_image_keys:      list[dict] | None
    objective_auto_score: float | None
    evaluations:          list[ScriptEvaluationResponse]


class AcceptSuggestionsRequest(BaseModel):
    """
    Evaluator accepts AI-suggested marks.
    question_ids=None → accept all questions.
    question_ids=[...] → accept only those specific questions.
    Skipped silently for questions where ai_suggested_marks is None.
    """
    question_ids:   list[str] | None = Field(
        default=None,
        description="UUIDs of questions to accept. Omit to accept all.",
    )
    evaluator_note: str | None = None


# ---------------------------------------------------------------------------
# Paper pipeline stats (H-36 STEP-10)
# ---------------------------------------------------------------------------

class PaperPipelineStats(BaseModel):
    """
    Aggregate pipeline-status counts for all scripts belonging to one exam paper.
    completion_pct = board_finalised / total * 100 (0.0 when total == 0).
    """
    paper_id:         UUID
    total:            int
    pending:          int
    quality_checking: int
    quality_failed:   int
    ocr_processing:   int
    processing:       int
    scored:           int
    failed:           int
    review_required:  int
    marks_submitted:  int
    board_finalised:  int
    completion_pct:   float
