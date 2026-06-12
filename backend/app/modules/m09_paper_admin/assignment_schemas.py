"""
M09.6 Assignment Engine — Pydantic schemas.

Anonymity rule: no response schema here exposes student identity.  Faculty-
facing responses carry only script_code / attempt_code.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.modules.m09_paper_admin.assignment_models import (
    AssignmentStatus,
    AssignmentType,
)

_VALID_TYPES = {t.value for t in AssignmentType}


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class AssignmentCreateRequest(BaseModel):
    """Manually allocate one work item to one evaluator."""
    assignment_type:  str
    target_entity:    str = Field(..., max_length=40)
    target_id:        UUID
    evaluator_id:     UUID
    exam_paper_id:    Optional[UUID] = None
    evaluation_round: str = "NONE"
    script_code:      Optional[str] = None
    attempt_code:     Optional[str] = None
    priority:         int = Field(default=0, ge=0, le=10)
    due_at:           Optional[datetime] = None
    notes:            Optional[str] = None

    @field_validator("assignment_type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        if v not in _VALID_TYPES:
            raise ValueError(f"assignment_type must be one of {sorted(_VALID_TYPES)}")
        return v


class BulkAssignmentItem(BaseModel):
    target_id:        UUID
    evaluator_id:     UUID
    evaluation_round: str = "NONE"
    script_code:      Optional[str] = None
    attempt_code:     Optional[str] = None


class BulkAssignmentRequest(BaseModel):
    """Allocate many explicit (item, evaluator) pairs in one transaction."""
    assignment_type: str
    target_entity:   str = Field(..., max_length=40)
    exam_paper_id:   Optional[UUID] = None
    priority:        int = Field(default=0, ge=0, le=10)
    due_at:          Optional[datetime] = None
    items:           list[BulkAssignmentItem] = Field(..., min_length=1)

    @field_validator("assignment_type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        if v not in _VALID_TYPES:
            raise ValueError(f"assignment_type must be one of {sorted(_VALID_TYPES)}")
        return v


class AutoAssignTargetItem(BaseModel):
    target_id:        UUID
    evaluation_round: str = "NONE"
    script_code:      Optional[str] = None
    attempt_code:     Optional[str] = None


class AutoAssignRequest(BaseModel):
    """
    Workload-balanced auto-allocation: distribute the supplied work items
    fairly across the evaluator pool.  ``dry_run`` returns the plan without
    persisting (preview for the Admin to ratify).
    """
    assignment_type: str
    target_entity:   str = Field(..., max_length=40)
    exam_paper_id:   Optional[UUID] = None
    evaluator_pool:  list[UUID] = Field(..., min_length=1)
    items:           list[AutoAssignTargetItem] = Field(..., min_length=1)
    priority:        int = Field(default=0, ge=0, le=10)
    due_at:          Optional[datetime] = None
    dry_run:         bool = False

    @field_validator("assignment_type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        if v not in _VALID_TYPES:
            raise ValueError(f"assignment_type must be one of {sorted(_VALID_TYPES)}")
        return v


class ReassignRequest(BaseModel):
    new_evaluator_id: UUID
    reason:           str = Field(..., min_length=3)


class CancelRequest(BaseModel):
    reason: str = Field(..., min_length=3)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class AssignmentResponse(BaseModel):
    id:               UUID
    assignment_type:  str
    status:           str
    target_entity:    str
    target_id:        UUID
    exam_paper_id:    Optional[UUID] = None
    evaluation_round: str
    script_code:      Optional[str] = None
    attempt_code:     Optional[str] = None
    evaluator_id:     UUID
    assigned_by:      UUID
    priority:         int
    due_at:           Optional[datetime] = None
    notes:            Optional[str] = None
    assigned_at:      datetime
    started_at:       Optional[datetime] = None
    submitted_at:     Optional[datetime] = None
    completed_at:     Optional[datetime] = None
    cancelled_at:     Optional[datetime] = None
    reassigned_from:  Optional[UUID] = None
    reassigned_to:    Optional[UUID] = None
    reassign_reason:  Optional[str] = None
    cancel_reason:    Optional[str] = None
    created_at:       datetime

    model_config = {"from_attributes": True}


class AssignmentListResponse(BaseModel):
    items:  list[AssignmentResponse]
    total:  int
    offset: int
    limit:  int


class WorkloadSummaryResponse(BaseModel):
    evaluator_id:         UUID
    active_count:         int
    pending_count:        int
    in_progress_count:    int
    submitted_count:      int
    completed_count:      int
    cancelled_count:      int
    reassigned_count:     int
    avg_turnaround_hours: Optional[float] = None


class WorkloadBoardResponse(BaseModel):
    """Workload across a pool — for Admin/Dean balancing views."""
    evaluators: list[WorkloadSummaryResponse]


class AutoAssignPlanItem(BaseModel):
    target_id:    UUID
    evaluator_id: UUID


class AutoAssignPreviewResponse(BaseModel):
    """Returned for dry_run=True — the proposed plan, nothing persisted."""
    dry_run:      bool = True
    plan:         list[AutoAssignPlanItem]
    distribution: dict[str, int]  # evaluator_id -> new item count


class AutoAssignResultResponse(BaseModel):
    """Returned for dry_run=False — created assignments + distribution."""
    dry_run:      bool = False
    created:      list[AssignmentResponse]
    skipped:      list[AutoAssignPlanItem]   # items already actively assigned
    distribution: dict[str, int]
