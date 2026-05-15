"""
M05 Learning Material Packager — Pydantic v2 schemas.

Conventions (matching M01/M02/M03):
  - from_attributes = True on every Response schema
  - Optional fields default to None in Update/Create schemas
  - Enums imported directly from .models (single source of truth)
  - JSONB columns returned as dict[str, Any] in Response schemas;
    structured sub-models (ItemMetadata) used for request-time validation
  - metadata_ SQLAlchemy attribute (avoids conflict with Base.metadata)
    mapped to JSON key "metadata" via validation_alias in PackageItemResponse

Module naming note:
  PackageItemResponse uses validation_alias="metadata_" so Pydantic reads
  obj.metadata_ from the ORM row but serialises the field as "metadata".
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.m05_learning_materials.models import (
    MaterialSourceType,
    PackageStatus,
    QARole,
)


# ---------------------------------------------------------------------------
# JSONB sub-models
# ---------------------------------------------------------------------------

class ItemMetadata(BaseModel):
    """
    Validated shape for PackageItem.metadata JSONB.

    Used in FacultyAddItemRequest and FacultyItemUpdate (request-time only).
    Response schemas return metadata as dict[str, Any] to avoid stale-key
    breakage as the schema evolves.

    Phase 2 reserved fields are present in schema but carry no runtime logic.
    """
    # YouTube / generic video
    thumbnail_url:       Optional[str]  = None
    duration_seconds:    Optional[int]  = Field(default=None, ge=0)
    # arXiv / paper
    arxiv_id:            Optional[str]  = None
    abstract_snippet:    Optional[str]  = None
    # Shared
    authors:             list[str]      = Field(default_factory=list)
    publish_date:        Optional[str]  = None   # ISO-8601 date string from source

    # ---- Phase 2 reserved — schema-ready, no logic in Phase 1 ----
    difficulty_level:     Optional[str]  = None   # "BEGINNER" | "INTERMEDIATE" | "ADVANCED"
    estimated_study_time: Optional[int]  = Field(default=None, ge=1)   # minutes
    learning_style_tags:  list[str]      = Field(default_factory=list)  # ["visual","reading",…]


class RAGSourceCitation(BaseModel):
    """
    One cited source embedded in a RAG assistant answer.
    Stored as a JSON object inside PackageQAMessage.sources JSONB list.
    """
    item_id:         UUID
    title:           str
    url:             Optional[str]   = None
    snippet:         str             = Field(..., min_length=1)
    relevance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Package item schemas
# ---------------------------------------------------------------------------

class PackageItemResponse(BaseModel):
    """
    Full item representation returned to callers.

    validation_alias="metadata_" maps the SQLAlchemy attribute (metadata_)
    to the serialised JSON key "metadata" without touching the model column.
    """
    model_config = {"from_attributes": True, "populate_by_name": True}

    id:                  UUID
    package_id:          UUID
    source_type:         MaterialSourceType
    title:               str
    url:                 Optional[str]
    content_hash:        Optional[str]
    metadata:            dict[str, Any]        = Field(
        default_factory=dict,
        validation_alias="metadata_",
    )
    relevance_score:     Optional[float]
    faculty_recommended: bool
    added_by_user_id:    Optional[UUID]
    display_order:       int
    qdrant_indexed:      bool
    created_at:          datetime
    updated_at:          Optional[datetime]


class FacultyAddItemRequest(BaseModel):
    """Faculty manually adds an external resource to a package."""
    source_type: MaterialSourceType = MaterialSourceType.FACULTY_NOTE
    title:       str                = Field(..., min_length=3, max_length=500)
    url:         Optional[str]      = None
    metadata:    ItemMetadata       = Field(default_factory=ItemMetadata)


class FacultyItemUpdate(BaseModel):
    """Partial update — faculty corrects title, URL, or metadata for any item."""
    title:    Optional[str]          = Field(default=None, min_length=3, max_length=500)
    url:      Optional[str]          = None
    metadata: Optional[ItemMetadata] = None


class FacultyRecommendToggle(BaseModel):
    """Toggle the Faculty Recommended badge on an item."""
    faculty_recommended: bool


class PackageItemReorder(BaseModel):
    """Maps item_id → new display_order for a batch reorder. Min one entry."""
    order: list[tuple[UUID, int]] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Learning package schemas
# ---------------------------------------------------------------------------

class LearningPackageResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:                 UUID
    syllabus_id:        UUID
    unit_number:        int
    version:            int
    status:             PackageStatus
    top_n:              int
    item_count:         int
    qdrant_indexed:     bool
    ai_model:           Optional[str]
    created_by_user_id: UUID
    curated_at:         Optional[datetime]
    created_at:         datetime
    updated_at:         Optional[datetime]


class LearningPackageDetail(LearningPackageResponse):
    """Full package with all items ordered by display_order."""
    items: list[PackageItemResponse]


class LearningPackageListResponse(BaseModel):
    total:     int
    page:      int
    page_size: int
    items:     list[LearningPackageResponse]


class PackageStatusResponse(BaseModel):
    """
    Lightweight status check — returned by every state-transition endpoint
    and by the polling route so the frontend can poll without fetching items.
    """
    model_config = {"from_attributes": True}

    id:             UUID
    syllabus_id:    UUID
    unit_number:    int
    version:        int
    status:         PackageStatus
    item_count:     int
    qdrant_indexed: bool
    curated_at:     Optional[datetime]
    updated_at:     Optional[datetime]


# ---------------------------------------------------------------------------
# Curation trigger schemas
# ---------------------------------------------------------------------------

class CurationTriggerRequest(BaseModel):
    """
    Faculty or admin triggers AI curation for one (syllabus, unit) pair.
    top_n overrides the institution default (M05_TOP_N_PER_UNIT) for this run.
    """
    syllabus_id: UUID
    unit_number: int           = Field(..., ge=1)
    top_n:       Optional[int] = Field(default=None, ge=1, le=50)


class CurationJobResponse(BaseModel):
    """Returned immediately when a curation Celery task is dispatched."""
    job_id:     UUID
    package_id: UUID
    status:     str = "queued"


# ---------------------------------------------------------------------------
# Q&A message schemas
# ---------------------------------------------------------------------------

class PackageQAMessageResponse(BaseModel):
    """
    A single turn in a Q&A session.
    sources is typed as list[RAGSourceCitation] — Pydantic v2 coerces each
    JSONB dict to RAGSourceCitation on ORM read.
    """
    model_config = {"from_attributes": True}

    id:         UUID
    session_id: UUID
    role:       QARole
    content:    str
    sources:    list[RAGSourceCitation] = Field(default_factory=list)
    created_at: datetime


# ---------------------------------------------------------------------------
# Q&A session schemas
# ---------------------------------------------------------------------------

class PackageQASessionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id:              UUID
    package_id:      UUID
    student_user_id: UUID
    created_at:      datetime
    updated_at:      Optional[datetime]


class PackageQASessionWithMessages(PackageQASessionResponse):
    """Full session with turn history, ordered by created_at asc."""
    messages: list[PackageQAMessageResponse]


# ---------------------------------------------------------------------------
# Student Q&A interaction schemas
# ---------------------------------------------------------------------------

class StudentQuestionRequest(BaseModel):
    """Student submits a natural-language question over the package content."""
    question: str = Field(..., min_length=5, max_length=1000)


class RAGAnswerResponse(BaseModel):
    """
    Returned synchronously after RAG generation completes.
    Both the persisted message_id and the full source citation list are
    included so the frontend can render citations without a second fetch.
    """
    session_id: UUID
    message_id: UUID
    answer:     str
    sources:    list[RAGSourceCitation] = Field(default_factory=list)
    model_used: Optional[str]           = None
