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

    # Double evaluation
    double_evaluation_enabled: bool = False
    primary_submitted_at:      datetime | None = None
    secondary_submitted_at:    datetime | None = None

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
    primary_total / secondary_total are None for single-evaluator papers.
    """
    id:                UUID
    script_id:         UUID
    exam_paper_id:     UUID
    student_user_id:   UUID | None
    student_roll_ref:  str | None
    total_marks:       float
    max_marks:         float
    primary_total:     float | None = None
    secondary_total:   float | None = None
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
# Quality-failed admin override (H-36 STEP-12)
# ---------------------------------------------------------------------------

class QualityOverrideRequest(BaseModel):
    """
    Admin overrides a QUALITY_FAILED script to proceed to OCR anyway.
    reason is mandatory — it is stored in the audit log.
    """
    reason: str = Field(..., min_length=10, description="Mandatory justification for overriding quality check.")


# ---------------------------------------------------------------------------
# Script file URL (H-36 STEP-13)
# ---------------------------------------------------------------------------

class ScriptFileUrlResponse(BaseModel):
    """
    Presigned GET URL for the uploaded script PDF/image.
    Generated on demand; expires in expires_in seconds (default 300).
    Only available when upload_url is set (physical paper path).
    """
    url:        str
    expires_in: int


# ---------------------------------------------------------------------------
# Paper pipeline stats (H-36 STEP-10)
# ---------------------------------------------------------------------------

class PaperPipelineStats(BaseModel):
    """
    Aggregate pipeline-status counts for all scripts belonging to one exam paper.
    completion_pct = board_finalised / total * 100 (0.0 when total == 0).
    """
    paper_id:                  UUID
    total:                     int
    pending:                   int
    quality_checking:          int
    quality_failed:            int
    ocr_processing:            int
    processing:                int
    scored:                    int
    failed:                    int
    review_required:           int
    waiting_second_evaluator:  int = 0
    secondary_evaluated:       int = 0
    marks_submitted:           int
    moderation_pending:        int = 0
    moderation_complete:       int = 0
    board_finalised:           int
    completion_pct:            float


# ---------------------------------------------------------------------------
# Board adjusted marks — per-question Board correction (M09.1)
# ---------------------------------------------------------------------------

class BoardAdjustEntry(BaseModel):
    """Board's adjusted mark for a single question."""
    board_adjusted_marks: float = Field(..., ge=0)
    board_adjustment_note: Optional[str] = None


class BoardAdjustRequest(BaseModel):
    """
    Board sets adjusted marks for all questions on a MARKS_SUBMITTED script.
    Required for double-evaluation papers before Board finalisation.
    Optional for single-evaluator papers (board can still adjust if needed).
    adjustments: {question_id (str UUID) → BoardAdjustEntry}
    """
    adjustments: dict[str, BoardAdjustEntry] = Field(
        ...,
        description="Mapping of question_id → Board adjusted mark.",
    )

    @model_validator(mode="after")
    def at_least_one(self) -> "BoardAdjustRequest":
        if not self.adjustments:
            raise ValueError("adjustments dict must contain at least one entry.")
        return self


# ---------------------------------------------------------------------------
# Board comparison view — three evaluation rounds for one script (M09.1)
# ---------------------------------------------------------------------------

class BoardComparisonResponse(BaseModel):
    """
    Board Gate 2 comparison view for a double-evaluated script.

    primary_evaluations:   PRIMARY round rows — evaluator marks + AI suggestions.
    secondary_evaluations: SECONDARY round rows — independent evaluator marks.
    primary_total:         Sum of primary evaluator_marks.
    secondary_total:       Sum of secondary evaluator_marks.
    max_marks_total:       Sum of max_marks across all questions.
    board_adjustments_set: True when all PRIMARY rows have board_adjusted_marks set.

    For single-evaluator papers secondary_evaluations is empty and
    secondary_total is 0.0.
    """
    script_id:               UUID
    masked_id:               str
    exam_paper_id:           UUID
    status:                  str
    double_evaluation_enabled: bool
    ocr_text:                str | None
    page_image_keys:         list[dict] | None

    primary_evaluations:     list[ScriptEvaluationResponse]
    secondary_evaluations:   list[ScriptEvaluationResponse]

    primary_total:           float
    secondary_total:         float
    max_marks_total:         float
    board_adjustments_set:   bool


# ---------------------------------------------------------------------------
# Moderation Workflow — M09.2
# ---------------------------------------------------------------------------

class ModerationFlagRequest(BaseModel):
    """Dean/Admin manually flags a MARKS_SUBMITTED script for moderation."""
    reason: str = Field(..., min_length=10, description="Mandatory justification for flagging.")


class ModerationMarkEntry(BaseModel):
    """Moderator's mark for a single question."""
    evaluator_marks: float = Field(..., ge=0)
    evaluator_note:  str | None = None


class ModerationSubmitRequest(BaseModel):
    """
    Moderator submits per-question marks for a MODERATION_PENDING script.
    marks: {question_id (str UUID) → ModerationMarkEntry}
    moderation_notes: mandatory narrative explaining the moderation decision.
    All questions from the PRIMARY round must be covered.
    """
    marks:            dict[str, ModerationMarkEntry] = Field(
        ...,
        description="Moderator's marks keyed by question_id (str UUID).",
    )
    moderation_notes: str = Field(
        ...,
        min_length=20,
        description="Mandatory explanation of the moderation decision.",
    )

    @model_validator(mode="after")
    def at_least_one(self) -> "ModerationSubmitRequest":
        if not self.marks:
            raise ValueError("marks dict must contain at least one entry.")
        return self


class ScriptVarianceResponse(BaseModel):
    """
    Primary vs secondary evaluator comparison — used before and during moderation.
    variance_pct = abs(primary_total - secondary_total) / max_marks_total * 100.
    exceeds_threshold = variance_pct > discrepancy_threshold_pct for this paper.
    """
    script_id:              UUID
    masked_id:              str
    exam_paper_id:          UUID
    status:                 str
    double_evaluation_enabled: bool
    primary_total:          float
    secondary_total:        float
    max_marks_total:        float
    variance_pct:           float
    threshold_pct:          float
    exceeds_threshold:      bool
    moderation_review_id:   Optional[UUID] = None
    moderation_status:      Optional[str]  = None


class ModerationReviewResponse(BaseModel):
    """Full moderation review record for a script."""
    id:                UUID
    script_id:         UUID
    exam_paper_id:     UUID
    primary_total:     float
    secondary_total:   float
    variance_pct:      float
    variance_threshold: float
    flag_reason:       str
    flagged_by:        Optional[UUID]
    flagged_at:        datetime
    moderator_id:      Optional[UUID]
    moderation_notes:  Optional[str]
    status:            str
    completed_at:      Optional[datetime]
    created_at:        datetime

    model_config = {"from_attributes": True}


class ModerationQueueResponse(BaseModel):
    """Paginated moderation queue for an exam paper."""
    items:  list[ModerationReviewResponse]
    total:  int
    offset: int
    limit:  int


class ModerationHistoryResponse(BaseModel):
    """
    Full moderation history for a script: review record + MODERATION round evaluations.
    """
    review:              Optional[ModerationReviewResponse]
    moderation_evals:    list[ScriptEvaluationResponse]
    primary_evals:       list[ScriptEvaluationResponse]
    secondary_evals:     list[ScriptEvaluationResponse]


# ---------------------------------------------------------------------------
# Board Approval — M09.4
# ---------------------------------------------------------------------------

class BoardSessionCreateRequest(BaseModel):
    """Dean/Admin convenes a board session for a paper's results."""
    exam_paper_id: UUID
    session_title: str = Field(..., min_length=5, description="Title for the board session.")
    pass_mark_pct: float = Field(
        default=40.0,
        ge=0.0,
        le=100.0,
        description="Pass threshold percentage for pass/fail computation.",
    )


class BoardApproveRequest(BaseModel):
    """Board casts approval of results."""
    board_remarks: Optional[str] = Field(
        default=None,
        description="Optional remarks from the Board.",
    )


class BoardRejectRequest(BaseModel):
    """Board rejects results and returns for re-evaluation."""
    board_remarks: str = Field(
        ..., min_length=20,
        description="Mandatory reason for rejection.",
    )


class BoardCourseApprovalResponse(BaseModel):
    """Aggregate statistics for an exam paper within a board session."""
    id:               UUID
    session_id:       UUID
    exam_paper_id:    UUID
    mean_marks:       Optional[float]
    max_marks:        Optional[float]
    pass_count:       Optional[int]
    fail_count:       Optional[int]
    total_scripts:    Optional[int]
    pass_rate_pct:    Optional[float]
    approval_status:  str
    created_at:       datetime

    model_config = {"from_attributes": True}


class BoardSessionResponse(BaseModel):
    """Full board session record."""
    id:              UUID
    exam_paper_id:   UUID
    session_title:   str
    convened_by:     UUID
    convened_at:     datetime
    status:          str
    board_remarks:   Optional[str]
    decided_by:      Optional[UUID]
    decided_at:      Optional[datetime]
    declared_by:     Optional[UUID]
    declared_at:     Optional[datetime]
    created_at:      datetime
    course_stats:    Optional[BoardCourseApprovalResponse] = None

    model_config = {"from_attributes": True}


class BoardSessionListResponse(BaseModel):
    """Paginated list of board sessions for a paper."""
    items:  list[BoardSessionResponse]
    total:  int
    offset: int
    limit:  int


class BoardStatisticsResponse(BaseModel):
    """Computed statistics for a board session."""
    session_id:        UUID
    exam_paper_id:     UUID
    total_finalised:   int
    total_scripts:     int
    mean_marks:        Optional[float]
    max_marks:         Optional[float]
    min_marks:         Optional[float]
    std_dev:           Optional[float]
    pass_count:        int
    fail_count:        int
    pass_rate_pct:     float
    pass_mark_pct:     float
    board_status:      str


# ---------------------------------------------------------------------------
# Revaluation Workflow — M09.3
# ---------------------------------------------------------------------------

class RevaluationCreateRequest(BaseModel):
    """Student submits a revaluation request for a script."""
    script_id:         UUID
    reason:            str = Field(..., min_length=20, description="Student's stated reason.")
    payment_reference: Optional[str] = None


class RevaluationAcceptRequest(BaseModel):
    """Admin accepts revaluation request and assigns an evaluator."""
    assigned_evaluator_id: UUID
    admin_notes:           Optional[str] = None


class RevaluationRejectRequest(BaseModel):
    """Admin rejects a revaluation request at intake."""
    admin_notes: str = Field(..., min_length=10, description="Mandatory rejection reason.")


class RevaluationMarkEntry(BaseModel):
    """Revaluator's mark for a single question."""
    revaluation_marks: float = Field(..., ge=0)
    evaluator_note:    Optional[str] = None


class RevaluationSubmitMarksRequest(BaseModel):
    """Revaluator submits per-question marks."""
    marks: dict[str, RevaluationMarkEntry] = Field(
        ...,
        description="Mapping of question_id (str UUID) → revaluation mark.",
    )
    submission_note: Optional[str] = None

    @model_validator(mode="after")
    def at_least_one(self) -> "RevaluationSubmitMarksRequest":
        if not self.marks:
            raise ValueError("marks dict must contain at least one entry.")
        return self


class RevaluationBoardRatifyRequest(BaseModel):
    """Board ratifies the revaluation outcome."""
    board_remarks: Optional[str] = None


class RevaluationBoardRejectRequest(BaseModel):
    """Board rejects the revaluation outcome."""
    board_remarks: str = Field(..., min_length=20, description="Mandatory rejection reason.")


class RevaluationEvaluationResponse(BaseModel):
    """Per-question revaluation marks."""
    id:                UUID
    request_id:        UUID
    question_id:       UUID
    question_type:     Optional[str]
    max_marks:         Optional[float]
    original_marks:    Optional[float]
    revaluation_marks: Optional[float]
    evaluator_note:    Optional[str]
    created_at:        datetime

    model_config = {"from_attributes": True}


class RevaluationRequestResponse(BaseModel):
    """Full revaluation request record."""
    id:                    UUID
    script_id:             UUID
    exam_paper_id:         UUID
    student_user_id:       UUID
    student_roll_ref:      Optional[str]
    original_total:        float
    max_marks:             float
    reason:                str
    payment_reference:     Optional[str]
    status:                str
    assigned_evaluator_id: Optional[UUID]
    revaluation_total:     Optional[float]
    awarded_total:         Optional[float]
    admin_notes:           Optional[str]
    board_remarks:         Optional[str]
    decided_by:            Optional[UUID]
    decided_at:            Optional[datetime]
    window_closes_at:      Optional[datetime]
    created_at:            datetime
    updated_at:            Optional[datetime]

    model_config = {"from_attributes": True}


class RevaluationRequestListResponse(BaseModel):
    """Paginated list of revaluation requests."""
    items:  list[RevaluationRequestResponse]
    total:  int
    offset: int
    limit:  int


class RevaluationDetailResponse(BaseModel):
    """Full revaluation request + per-question evaluations."""
    request:     RevaluationRequestResponse
    evaluations: list[RevaluationEvaluationResponse]


# ---------------------------------------------------------------------------
# Digital Exams — M09.5
# ---------------------------------------------------------------------------

class DigitalSessionCreate(BaseModel):
    exam_paper_id:     UUID
    title:             str = Field(..., min_length=3, max_length=200)
    max_duration_mins: int = Field(default=180, ge=10, le=600)
    window_start:      Optional[datetime] = None
    window_end:        Optional[datetime] = None
    instructions:      Optional[str] = None


class DigitalSessionResponse(BaseModel):
    id:                UUID
    exam_paper_id:     UUID
    created_by:        UUID
    title:             str
    status:            str
    max_duration_mins: int
    window_start:      Optional[datetime]
    window_end:        Optional[datetime]
    instructions:      Optional[str]
    activated_at:      Optional[datetime]
    closed_at:         Optional[datetime]
    created_at:        datetime
    attempt_count:     int = 0
    scored_count:      int = 0

    model_config = {"from_attributes": True}


class DigitalSessionListResponse(BaseModel):
    items:  list[DigitalSessionResponse]
    total:  int
    offset: int
    limit:  int


class DigitalAttemptResponse(BaseModel):
    id:              UUID
    session_id:      UUID
    student_user_id: UUID
    status:          str
    started_at:      datetime
    expires_at:      Optional[datetime]
    submitted_at:    Optional[datetime]
    auto_scored_at:  Optional[datetime]
    auto_score:      Optional[float]
    mcq_max_score:   Optional[float]
    created_at:      datetime

    model_config = {"from_attributes": True}


class DigitalResponseIn(BaseModel):
    """Student saves one answer (MCQ or subjective)."""
    selected_option: Optional[str] = Field(default=None, max_length=4)
    response_text:   Optional[str] = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "DigitalResponseIn":
        if self.selected_option is None and self.response_text is None:
            raise ValueError("Provide selected_option or response_text")
        return self


class DigitalResponseOut(BaseModel):
    id:              UUID
    attempt_id:      UUID
    question_id:     UUID
    question_type:   Optional[str]
    selected_option: Optional[str]
    response_text:   Optional[str]
    is_auto_scored:  bool
    auto_score:      Optional[float]
    is_correct:      Optional[bool]
    answered_at:     Optional[datetime]

    model_config = {"from_attributes": True}


class DigitalQuestionOut(BaseModel):
    """Question data served to students — correct answers never included."""
    id:            UUID
    unit_number:   int
    question_type: str
    bloom_level:   str
    question_text: str
    options:       Optional[list[dict]]
    marks:         float
    section_label: Optional[str]
    choice_group:  Optional[int]
    # student's saved response for this question (if any)
    saved_response: Optional[DigitalResponseOut] = None


class DigitalAttemptDetailResponse(BaseModel):
    attempt:    DigitalAttemptResponse
    questions:  list[DigitalQuestionOut]


class DigitalResultResponse(BaseModel):
    """Result view after scoring."""
    attempt:      DigitalAttemptResponse
    responses:    list[DigitalResponseOut]
    total_questions:    int
    mcq_questions:      int
    subjective_questions: int
    attempted_count:    int
    correct_mcq:        int


# ---------------------------------------------------------------------------
# M09.5 Dean Analytics
# ---------------------------------------------------------------------------

class DigitalScoreBucket(BaseModel):
    label:   str    # e.g. "0–10 %"
    pct_lo:  int
    pct_hi:  int
    count:   int


class DigitalSessionAnalyticsResponse(BaseModel):
    """Per-session analytics for Dean / Admin / Board."""
    session_id:         str
    title:              str
    status:             str
    attempt_count:      int
    scored_count:       int
    in_progress_count:  int
    avg_score_pct:      Optional[float]    # 0–100
    min_score_pct:      Optional[float]
    max_score_pct:      Optional[float]
    median_score_pct:   Optional[float]
    pass_count:         int
    fail_count:         int
    pass_rate_pct:      Optional[float]
    pass_threshold_pct: float              # configurable; default 40 %
    score_buckets:      list[DigitalScoreBucket]
