"""
M09.9 Compliance & Audit — Pydantic schemas (read-only).

These are response shapes only.  The compliance subsystem never accepts a body
that mutates examination data; the sole write path is the internal, append-only
``exam_mark_audit`` recorder invoked by the evaluation service.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Timeline / audit trail
# ---------------------------------------------------------------------------

class TimelineEntryResponse(BaseModel):
    id:             str
    event_type:     str
    category:       str
    label:          str
    actor_user_id:  Optional[str] = None
    actor_role:     Optional[str] = None
    actor_name:     Optional[str] = None
    target_entity:  Optional[str] = None
    target_id:      Optional[str] = None
    occurred_at:    datetime
    metadata:       dict[str, Any] = Field(default_factory=dict)


class AuditTrailResponse(BaseModel):
    scope:            str                       # STUDENT / SCRIPT / EXAM / EVALUATOR / DATE_RANGE / INSTITUTION
    scope_ref:        Optional[str] = None      # the id the trail is scoped to
    total:            int
    page:             int
    page_size:        int
    category_counts:  dict[str, int] = Field(default_factory=dict)
    entries:          list[TimelineEntryResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Mark-change history (field-level + derived lineage)
# ---------------------------------------------------------------------------

class MarkAuditEntryResponse(BaseModel):
    id:               str
    script_id:        str
    exam_paper_id:    str
    question_id:      Optional[str] = None
    evaluation_round: Optional[str] = None
    change_type:      str
    previous_marks:   Optional[float] = None
    new_marks:        Optional[float] = None
    max_marks:        Optional[float] = None
    delta:            Optional[float] = None
    actor_user_id:    str
    actor_role:       Optional[str] = None
    actor_name:       Optional[str] = None
    reason:           Optional[str] = None
    source_event:     Optional[str] = None
    masked_id:        Optional[str] = None
    created_at:       datetime


class MarkLineageStepResponse(BaseModel):
    stage:     str
    marks:     Optional[float] = None
    max_marks: Optional[float] = None
    note:      Optional[str] = None


class QuestionMarkHistoryResponse(BaseModel):
    question_id:   str
    question_type: Optional[str] = None
    max_marks:     Optional[float] = None
    steps:         list[MarkLineageStepResponse] = Field(default_factory=list)


class ResultChangeHistoryResponse(BaseModel):
    script_id:        str
    exam_paper_id:    Optional[str] = None
    masked_id:        Optional[str] = None
    student_revealed: bool = False
    student_user_id:  Optional[str] = None
    # Field-level recorded mutations (exam_mark_audit)
    recorded_changes: list[MarkAuditEntryResponse] = Field(default_factory=list)
    # Derived per-question lineage (from evaluation snapshots)
    question_history: list[QuestionMarkHistoryResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Compliance report rows
# ---------------------------------------------------------------------------

class PublicationApprovalRow(BaseModel):
    exam_paper_id:   str
    exam_paper_title: Optional[str] = None
    session_id:      Optional[str] = None
    convened_by:     Optional[str] = None
    convened_by_name: Optional[str] = None
    convened_at:     Optional[datetime] = None
    decided_by:      Optional[str] = None
    decided_by_name: Optional[str] = None
    decided_at:      Optional[datetime] = None
    declared_by:     Optional[str] = None
    declared_by_name: Optional[str] = None
    declared_at:     Optional[datetime] = None
    status:          str
    board_remarks:   Optional[str] = None


class ModerationReportRow(BaseModel):
    review_id:        str
    script_id:        str
    masked_id:        Optional[str] = None
    exam_paper_id:    str
    primary_total:    Optional[float] = None
    secondary_total:  Optional[float] = None
    variance_pct:     Optional[float] = None
    variance_threshold: Optional[float] = None
    flag_reason:      Optional[str] = None
    flagged_by:       Optional[str] = None
    flagged_by_name:  Optional[str] = None
    moderator_id:     Optional[str] = None
    moderator_name:   Optional[str] = None
    moderation_notes: Optional[str] = None
    status:           str
    flagged_at:       Optional[datetime] = None
    completed_at:     Optional[datetime] = None


class RevaluationReportRow(BaseModel):
    request_id:       str
    script_id:        str
    exam_paper_id:    str
    status:           str
    original_total:   Optional[float] = None
    revaluation_total: Optional[float] = None
    awarded_total:    Optional[float] = None
    delta:            Optional[float] = None
    assigned_evaluator_id: Optional[str] = None
    assigned_evaluator_name: Optional[str] = None
    decided_by:       Optional[str] = None
    decided_by_name:  Optional[str] = None
    decided_at:       Optional[datetime] = None
    reason:           Optional[str] = None
    board_remarks:    Optional[str] = None
    created_at:       Optional[datetime] = None


class EvaluatorActivityRow(BaseModel):
    evaluator_id:      str
    evaluator_name:    Optional[str] = None
    scripts_assigned:  int = 0
    scripts_submitted: int = 0
    mark_changes:      int = 0
    board_adjustments_on_their_scripts: int = 0
    last_activity_at:  Optional[datetime] = None


class BoardApprovalRow(BaseModel):
    session_id:    str
    exam_paper_id: str
    exam_paper_title: Optional[str] = None
    session_title: Optional[str] = None
    status:        str
    convened_by:   Optional[str] = None
    convened_by_name: Optional[str] = None
    convened_at:   Optional[datetime] = None
    decided_by:    Optional[str] = None
    decided_by_name: Optional[str] = None
    decided_at:    Optional[datetime] = None
    pass_rate_pct: Optional[float] = None
    mean_marks:    Optional[float] = None
    total_scripts: Optional[int] = None
    board_remarks: Optional[str] = None


class ReportResponse(BaseModel):
    """Generic report envelope — `report` names which report, `rows` is its payload."""
    report:       str
    exam_paper_id: Optional[str] = None
    generated_at: datetime
    row_count:    int
    rows:         list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dashboard bundle
# ---------------------------------------------------------------------------

class ComplianceKpis(BaseModel):
    total_events:         int = 0
    mark_changes:         int = 0
    board_adjustments:    int = 0
    moderations:          int = 0
    revaluations:         int = 0
    board_approvals:      int = 0
    publications:         int = 0
    open_revaluations:    int = 0
    pending_moderations:  int = 0


class ComplianceDashboardResponse(BaseModel):
    scope:           str
    exam_paper_id:   Optional[str] = None
    kpis:            ComplianceKpis
    category_counts: dict[str, int] = Field(default_factory=dict)
    recent_events:   list[TimelineEntryResponse] = Field(default_factory=list)
