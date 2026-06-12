"""
M09.8 Examination Analytics — Pydantic response schemas.

All schemas are response-only (analytics is read-only).  Percentages are 0–100
floats.  Optional/None fields render as an "empty state" on the frontend rather
than 0, so a subject with no data is visibly distinct from a subject where
everyone scored 0.
"""
from __future__ import annotations

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Examination Overview
# ---------------------------------------------------------------------------

class OverviewResponse(BaseModel):
    scope:              str            # "INSTITUTION" or "PAPER"
    exam_paper_id:      str | None
    exam_paper_title:   str | None
    total_students:     int
    appeared:           int
    absent:             int
    pass_count:         int
    fail_count:         int
    pass_pct:           float | None
    average_pct:        float | None
    highest_pct:        float | None
    lowest_pct:         float | None
    pass_threshold_pct: float
    papers_count:       int            # number of exam papers in scope


# ---------------------------------------------------------------------------
# Subject Analytics
# ---------------------------------------------------------------------------

class SubjectStatResponse(BaseModel):
    exam_paper_id:    str
    exam_paper_title: str | None
    course_code:      str | None
    course_title:     str | None
    count:            int
    average:          float | None
    median:           float | None
    highest:          float | None
    lowest:           float | None
    pass_count:       int
    fail_count:       int
    pass_pct:         float | None
    fail_pct:         float | None


class SubjectAnalyticsResponse(BaseModel):
    pass_threshold_pct: float
    subjects:           list[SubjectStatResponse]


# ---------------------------------------------------------------------------
# Faculty Analytics
# ---------------------------------------------------------------------------

class FacultyStatResponse(BaseModel):
    evaluator_id:          str
    evaluator_name:        str | None
    scripts_evaluated:     int
    average_awarded_pct:   float | None
    average_awarded_marks: float | None
    avg_turnaround_hours:  float | None


class FacultyAnalyticsResponse(BaseModel):
    institution_avg_awarded_pct: float | None   # benchmark for "unusual marking"
    faculty:                     list[FacultyStatResponse]


# ---------------------------------------------------------------------------
# Batch Analytics
# ---------------------------------------------------------------------------

class BatchStatResponse(BaseModel):
    admission_year: int | None
    label:          str            # "2023 Batch" / "Unknown batch"
    count:          int
    average:        float | None
    pass_pct:       float | None
    topper_pct:     float | None
    topper_user_id: str | None


class BatchAnalyticsResponse(BaseModel):
    pass_threshold_pct: float
    batches:            list[BatchStatResponse]


# ---------------------------------------------------------------------------
# Grade Distribution
# ---------------------------------------------------------------------------

class GradeBucketResponse(BaseModel):
    grade:        str
    count:        int
    pct_of_total: float


class GradeAnalyticsResponse(BaseModel):
    total_scripts: int
    buckets:       list[GradeBucketResponse]


# ---------------------------------------------------------------------------
# Revaluation Analytics
# ---------------------------------------------------------------------------

class RevaluationAnalyticsResponse(BaseModel):
    total_requests:   int
    decided:          int
    pending:          int
    marks_increased:  int
    marks_unchanged:  int
    average_increase: float | None
    max_increase:     float | None


# ---------------------------------------------------------------------------
# Moderation Analytics
# ---------------------------------------------------------------------------

class ModerationAnalyticsResponse(BaseModel):
    scripts_moderated:    int
    completed:            int
    pending:              int
    average_variance_pct: float | None
    average_delta:        float | None


# ---------------------------------------------------------------------------
# Dashboard bundle — one round-trip for a dashboard landing page
# ---------------------------------------------------------------------------

class DashboardResponse(BaseModel):
    overview:    OverviewResponse
    grades:      GradeAnalyticsResponse
    top_subjects:    list[SubjectStatResponse]    # hardest subjects (lowest avg)
    revaluation: RevaluationAnalyticsResponse
    moderation:  ModerationAnalyticsResponse
