"""
M10 Bell Curve Normaliser — Pydantic schemas.

All enum fields use Python Enum classes for API validation.
Serialization to/from DB uses .value (sa.String columns).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.modules.m10_bell_curve.models import (
    AnalysisStatus,
    BoardDecision,
    NormalisationMethod,
)


# ---------------------------------------------------------------------------
# Sub-models for JSONB payloads
# ---------------------------------------------------------------------------

class HistogramBin(BaseModel):
    bin_start: float
    bin_end:   float
    count:     int


class RawStats(BaseModel):
    mean:      float
    std:       float
    median:    float
    min:       float
    max:       float
    skewness:  float
    kurtosis:  float
    q1:        float
    q3:        float
    histogram: list[HistogramBin] = Field(default_factory=list)


class AnomalyItem(BaseModel):
    type:           str   # ZERO_INFLATION | CEILING_EFFECT | BIMODAL | EXCESSIVE_SKEW
    severity:       str   # WARNING | CRITICAL
    description:    str
    threshold:      float
    observed_value: float


class CrossEvaluatorStat(BaseModel):
    evaluator_id: UUID
    mean:         float
    std:          float
    count:        int
    z_score:      float
    is_outlier:   bool


class ProjectedStats(BaseModel):
    mean:     float
    std:      float
    median:   float
    min:      float
    max:      float
    skewness: float


class NormalisationSuggestion(BaseModel):
    method:          NormalisationMethod
    params:          dict[str, Any] = Field(default_factory=dict)
    reasoning:       str
    projected_stats: ProjectedStats | None = None


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class TriggerAnalysisRequest(BaseModel):
    exam_paper_id: UUID = Field(..., description="M08 exam_papers.id to analyse")


class PreviewNormalisationRequest(BaseModel):
    method: NormalisationMethod
    params: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "LINEAR_SCALE: {scale_factor}; "
            "PERCENTILE_MAP: {target_mean, target_max}; "
            "BOUNDARY_SHIFT: {shift_amount, direction}; "
            "NONE: {}; "
            "CUSTOM: {adjustments: [{student_roll_ref, delta}]}"
        ),
    )


class RatifyRequest(BaseModel):
    decision:              BoardDecision
    normalisation_method:  NormalisationMethod
    normalisation_params:  dict[str, Any] = Field(default_factory=dict)
    ratification_note:     str | None = None

    @model_validator(mode="after")
    def _check_rejected_uses_none(self) -> "RatifyRequest":
        if self.decision == BoardDecision.REJECTED:
            self.normalisation_method = NormalisationMethod.NONE
            self.normalisation_params = {}
        return self


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class BellCurveAnalysisResponse(BaseModel):
    id:                       UUID
    exam_paper_id:            UUID
    analysis_job_id:          UUID | None
    score_count:              int | None
    raw_stats:                RawStats | None
    anomalies:                list[AnomalyItem] | None
    normalisation_suggestion: NormalisationSuggestion | None
    cross_evaluator_stats:    list[CrossEvaluatorStat] | None
    triggered_by:             UUID
    status:                   AnalysisStatus
    triggered_at:             datetime | None
    analysis_completed_at:    datetime | None
    created_at:               datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _coerce_jsonb(cls, data: Any) -> Any:
        if hasattr(data, "__dict__"):
            return data
        return data


class BellCurveAnalysisListResponse(BaseModel):
    items:  list[BellCurveAnalysisResponse]
    total:  int
    offset: int
    limit:  int


class BellCurveDecisionResponse(BaseModel):
    id:                   UUID
    analysis_id:          UUID
    exam_paper_id:        UUID
    decision:             BoardDecision
    normalisation_method: NormalisationMethod
    normalisation_params: dict[str, Any]
    projected_stats:      ProjectedStats | None
    ratified_by:          UUID
    ratification_note:    str | None
    ratified_at:          datetime

    model_config = {"from_attributes": True}


class BellCurveDecisionListResponse(BaseModel):
    items:  list[BellCurveDecisionResponse]
    total:  int
    offset: int
    limit:  int


class NormalisedScoreResponse(BaseModel):
    id:                   UUID
    decision_id:          UUID
    analysis_id:          UUID
    exam_paper_id:        UUID
    student_user_id:      UUID | None
    student_roll_ref:     str | None
    raw_score:            float
    normalised_score:     float
    max_marks:            float
    normalisation_method: str
    created_at:           datetime

    # Grade enrichment — derived from normalised_score/max_marks at serialization time; never stored in DB
    pct:          float | None = None
    grade_letter: str   | None = None
    grade_point:  float | None = None
    is_pass:      bool  | None = None

    model_config = {"from_attributes": True}


class NormalisedScoreListResponse(BaseModel):
    items:  list[NormalisedScoreResponse]
    total:  int
    offset: int
    limit:  int


class TriggerAnalysisResponse(BaseModel):
    analysis_id: UUID
    job_id:      UUID
    status:      AnalysisStatus


class PreviewNormalisationResponse(BaseModel):
    method:          NormalisationMethod
    params:          dict[str, Any]
    projected_stats: ProjectedStats
    score_deltas:    list[dict[str, Any]]  # [{student_roll_ref, raw, normalised}]


class RatifyResponse(BaseModel):
    analysis_id:  UUID
    decision_id:  UUID
    decision:     BoardDecision
    method:       NormalisationMethod
    scores_written: int  # number of normalised score rows created (0 if REJECTED)


class GradeSummaryResponse(BaseModel):
    exam_paper_id: UUID
    total:         int
    pass_count:    int
    fail_count:    int
    pass_rate:     float          # 0.0 – 100.0, rounded to 1 decimal; advisory only
    grade_counts:  dict[str, int] # {"S": 2, "A": 5, …} — only grades that appear
