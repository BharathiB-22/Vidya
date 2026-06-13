"""
M09.7 OCR Review Queue — Pydantic schemas.

Naming convention mirrors the module pattern:
  *Create  — request body for resource creation / update
  *Response — API response model
  *Request — workflow action body
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Threshold configuration
# ---------------------------------------------------------------------------

class OcrThresholdCreate(BaseModel):
    """Admin sets or updates a confidence threshold for a given scope."""
    scope: str = Field(
        ...,
        pattern="^(GLOBAL|EXAM)$",
        description="GLOBAL = institution default; EXAM = override for one exam paper.",
    )
    scope_ref_id: Optional[UUID] = Field(
        default=None,
        description="exam_paper_id when scope=EXAM; omit for GLOBAL.",
    )
    low_confidence_threshold: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
        description="Scripts with OCR confidence below this value enter the LOW_CONFIDENCE queue.",
    )
    medium_confidence_threshold: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Scripts with confidence in [low, medium) enter the MEDIUM_CONFIDENCE queue.",
    )


class OcrThresholdResponse(BaseModel):
    id:                          UUID
    scope:                       str
    scope_ref_id:                Optional[UUID]
    low_confidence_threshold:    float
    medium_confidence_threshold: float
    is_active:                   bool
    created_by:                  UUID
    created_at:                  datetime
    updated_at:                  Optional[datetime]

    model_config = {"from_attributes": True}


class EffectiveThresholdResponse(BaseModel):
    """Resolved threshold for a given exam paper (EXAM override > GLOBAL default)."""
    low_confidence_threshold:    float
    medium_confidence_threshold: float
    source_scope:                str   # "GLOBAL" or "EXAM"
    source_id:                   Optional[str] = None


# ---------------------------------------------------------------------------
# Queue dashboard counters
# ---------------------------------------------------------------------------

class OcrDashboardResponse(BaseModel):
    """Priority-category counters for the OCR review dashboard."""
    pending_total:      int = 0
    in_review_total:    int = 0
    ocr_failure_count:  int = 0
    low_confidence_count: int = 0
    quality_issue_count:  int = 0
    medium_confidence_count: int = 0
    completed_today:    int = 0


# ---------------------------------------------------------------------------
# Queue list item
# ---------------------------------------------------------------------------

class OcrQueueItem(BaseModel):
    """One row in the OCR review queue list."""
    id:                   UUID
    script_id:            UUID
    exam_paper_id:        UUID
    masked_id:            Optional[str] = None   # from scanned_scripts
    priority_category:    str
    priority_score:       int
    ocr_confidence:       Optional[float]
    review_status:        str
    assigned_reviewer_id: Optional[UUID]
    review_started_at:    Optional[datetime]
    action_taken:         Optional[str]
    completed_at:         Optional[datetime]
    created_at:           datetime

    model_config = {"from_attributes": True}


class OcrQueueListResponse(BaseModel):
    items:  list[OcrQueueItem]
    total:  int
    offset: int
    limit:  int


# ---------------------------------------------------------------------------
# Queue detail (includes script context + image keys for viewer)
# ---------------------------------------------------------------------------

class OcrReviewDetailResponse(BaseModel):
    """
    Full OCR review context for the reviewer panel.

    Combines the queue record with the script's current state so the reviewer
    can see the scan images alongside the OCR text without a separate call.
    """
    queue_id:             UUID
    script_id:            UUID
    exam_paper_id:        UUID
    masked_id:            Optional[str]
    priority_category:    str
    priority_score:       int
    review_status:        str

    # OCR data (snapshot taken when script entered the queue)
    original_ocr_text:    Optional[str]
    ocr_confidence:       Optional[float]
    corrected_text:       Optional[str]        # set only after CORRECTED action

    # Scan quality context
    ocr_status:           Optional[str]        # from scanned_scripts
    ocr_quality_score:    Optional[float]      # from scanned_scripts
    scan_quality_flags:   Optional[list[dict]] # from scanned_scripts

    # Image viewer data
    page_count:           Optional[int]
    page_image_keys:      Optional[list[dict]] # [{page_no, s3_key}]

    # Review meta
    assigned_reviewer_id: Optional[UUID]
    review_started_at:    Optional[datetime]
    reviewer_notes:       Optional[str]
    action_taken:         Optional[str]
    completed_by:         Optional[UUID]
    completed_at:         Optional[datetime]
    created_at:           datetime


# ---------------------------------------------------------------------------
# Review action request bodies
# ---------------------------------------------------------------------------

class OcrStartReviewRequest(BaseModel):
    """Reviewer opens a queue item for review. No body required; kept for future extension."""
    pass


class OcrAcceptRequest(BaseModel):
    reviewer_notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Optional note recorded for compliance.",
    )


class OcrCorrectRequest(BaseModel):
    corrected_text: str = Field(
        ...,
        min_length=1,
        description="Corrected OCR text as entered by the human reviewer.",
    )
    reviewer_notes: Optional[str] = Field(
        default=None,
        max_length=2000,
    )


class OcrRerunRequest(BaseModel):
    reviewer_notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Reason for requesting re-extraction (optional).",
    )


class OcrEscalateRequest(BaseModel):
    reviewer_notes: str = Field(
        ...,
        min_length=10,
        description="Mandatory justification for escalation.",
    )


class OcrUnreadableRequest(BaseModel):
    reviewer_notes: str = Field(
        ...,
        min_length=10,
        description="Mandatory explanation of why the script cannot be read.",
    )


# ---------------------------------------------------------------------------
# Action response
# ---------------------------------------------------------------------------

class OcrActionResponse(BaseModel):
    """Response returned after any OCR review action."""
    queue_id:      UUID
    script_id:     UUID
    review_status: str
    action_taken:  Optional[str]
    completed_at:  Optional[datetime]
    message:       str
