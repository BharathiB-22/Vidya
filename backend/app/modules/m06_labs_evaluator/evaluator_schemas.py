"""
M06 — Pydantic schemas for the EVALUATOR workflow.

These schemas handle evaluator assignment management and evaluator-specific
review/recommendation actions.  Faculty schemas live in schemas.py.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Evaluator assignment management (faculty assigns evaluator to a lab)
# ---------------------------------------------------------------------------

class EvaluatorAssignRequest(BaseModel):
    evaluator_user_id: UUID


class EvaluatorAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                  UUID
    assignment_id:       UUID
    evaluator_user_id:   UUID
    assigned_by_user_id: UUID
    assigned_at:         datetime
    is_active:           bool


class EvaluatorAssignmentList(BaseModel):
    items: list[EvaluatorAssignmentResponse]
    total: int


# ---------------------------------------------------------------------------
# Evaluator recommendation (score + note, NOT finalization)
# ---------------------------------------------------------------------------

class EvaluatorCriterionScore(BaseModel):
    criterion_id: str
    human_score:  float
    human_note:   str | None = None


class EvaluatorRecommendRequest(BaseModel):
    scores: list[EvaluatorCriterionScore]
    recommendation_note: str | None = None


# ---------------------------------------------------------------------------
# Evaluator analytics summary
# ---------------------------------------------------------------------------

class EvaluatorAnalytics(BaseModel):
    total_assigned:   int
    total_submissions: int
    pending_review:   int
    recommended:      int
    ratified:         int
