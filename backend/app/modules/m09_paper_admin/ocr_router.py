"""
M09.7 OCR Review Queue — Router.

Mounted at /ocr-review (see main.py).

RBAC
----
  _ADMIN_ONLY = ADMIN                — threshold config (write)
  _REVIEWER   = ADMIN + FACULTY      — review queue read + actions
  _READ       = ADMIN + DEAN + BOARD — dashboard + queue read (governance view)

Route summary
-------------
  GET  /ocr-review/dashboard                   — priority category counters
  GET  /ocr-review                             — paginated queue (PENDING/IN_REVIEW)
  GET  /ocr-review/{queue_id}                  — detail with script context + image keys
  POST /ocr-review/{queue_id}/start            — start review (sets IN_REVIEW)
  POST /ocr-review/{queue_id}/accept           — accept OCR as-is
  POST /ocr-review/{queue_id}/correct          — submit corrected OCR text
  POST /ocr-review/{queue_id}/rerun            — request OCR re-extraction
  POST /ocr-review/{queue_id}/escalate         — escalate to Admin
  POST /ocr-review/{queue_id}/unreadable       — mark physically unreadable

  GET  /ocr-review/threshold                   — get effective threshold
  POST /ocr-review/threshold                   — set/update threshold (ADMIN)
  GET  /ocr-review/threshold/all               — list all threshold configs (ADMIN)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_context_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m09_paper_admin.ocr_schemas import (
    EffectiveThresholdResponse,
    OcrAcceptRequest,
    OcrActionResponse,
    OcrCorrectRequest,
    OcrDashboardResponse,
    OcrEscalateRequest,
    OcrQueueListResponse,
    OcrRerunRequest,
    OcrReviewDetailResponse,
    OcrStartReviewRequest,
    OcrThresholdCreate,
    OcrThresholdResponse,
    OcrUnreadableRequest,
)
from app.modules.m09_paper_admin.ocr_service import (
    OcrReviewService,
    OcrServiceError,
    OcrThresholdService,
)

router = APIRouter(tags=["M09.7 OCR Review Queue"])

_ADMIN_ONLY = [TenantRole.ADMIN]
_REVIEWER   = [TenantRole.ADMIN, TenantRole.FACULTY]
_READ       = [TenantRole.ADMIN, TenantRole.DEAN, TenantRole.BOARD]


def _admin_dep():    return require_roles(*_ADMIN_ONLY)
def _reviewer_dep(): return require_roles(*_REVIEWER)
def _read_dep():     return require_roles(*_READ)


def _raise(err: OcrServiceError):
    raise HTTPException(status_code=err.status_code, detail=err.message)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=OcrDashboardResponse)
async def get_dashboard(
    exam_paper_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Priority-category counters for the OCR review landing dashboard."""
    db: AsyncSession = db_info["db"]
    return await OcrReviewService.get_dashboard(exam_paper_id, db=db)


# ---------------------------------------------------------------------------
# Threshold config — must be declared before /{queue_id} to avoid collision
# ---------------------------------------------------------------------------

@router.get("/threshold/all", response_model=list[OcrThresholdResponse])
async def list_thresholds(
    current_user: CurrentUser = Depends(_admin_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """List all threshold configurations (ADMIN only)."""
    db: AsyncSession = db_info["db"]
    return await OcrThresholdService.list_all(db=db)


@router.get("/threshold", response_model=EffectiveThresholdResponse)
async def get_effective_threshold(
    exam_paper_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Resolved confidence thresholds for a given exam paper (EXAM > GLOBAL)."""
    db: AsyncSession = db_info["db"]
    return await OcrThresholdService.get_effective(exam_paper_id, db=db)


@router.post("/threshold", response_model=OcrThresholdResponse)
async def set_threshold(
    body: OcrThresholdCreate,
    current_user: CurrentUser = Depends(_admin_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Create or update a confidence threshold config (ADMIN only)."""
    db: AsyncSession = db_info["db"]
    try:
        return await OcrThresholdService.set_threshold(
            scope=body.scope,
            scope_ref_id=body.scope_ref_id,
            low_threshold=body.low_confidence_threshold,
            medium_threshold=body.medium_confidence_threshold,
            current_user=current_user,
            db=db,
            tenant_id=db_info["tenant_id"],
        )
    except OcrServiceError as e:
        _raise(e)


# ---------------------------------------------------------------------------
# Queue read
# ---------------------------------------------------------------------------

@router.get("", response_model=OcrQueueListResponse)
async def list_queue(
    exam_paper_id: UUID | None     = Query(default=None),
    priority_category: str | None  = Query(default=None),
    show_completed: bool           = Query(default=False),
    offset: int                    = Query(default=0, ge=0),
    limit: int                     = Query(default=50, ge=1, le=200),
    current_user: CurrentUser      = Depends(_reviewer_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Paginated OCR review queue, ordered by priority (highest first)."""
    db: AsyncSession = db_info["db"]
    return await OcrReviewService.get_queue(
        exam_paper_id=exam_paper_id,
        priority_category=priority_category,
        show_completed=show_completed,
        offset=offset,
        limit=limit,
        db=db,
    )


@router.get("/{queue_id}", response_model=OcrReviewDetailResponse)
async def get_detail(
    queue_id: UUID,
    current_user: CurrentUser = Depends(_reviewer_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Full OCR review context — image keys, original text, quality flags."""
    db: AsyncSession = db_info["db"]
    try:
        return await OcrReviewService.get_detail(queue_id, db=db)
    except OcrServiceError as e:
        _raise(e)


# ---------------------------------------------------------------------------
# Review actions
# ---------------------------------------------------------------------------

@router.post("/{queue_id}/start", response_model=OcrActionResponse)
async def start_review(
    queue_id: UUID,
    _body: OcrStartReviewRequest = OcrStartReviewRequest(),
    current_user: CurrentUser = Depends(_reviewer_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Mark the queue item as IN_REVIEW and assign the current user as reviewer."""
    db: AsyncSession = db_info["db"]
    try:
        result = await OcrReviewService.start_review(
            queue_id, current_user, db=db, tenant_id=db_info["tenant_id"]
        )
    except OcrServiceError as e:
        _raise(e)
    await db.commit()
    return result


@router.post("/{queue_id}/accept", response_model=OcrActionResponse)
async def accept_ocr(
    queue_id: UUID,
    body: OcrAcceptRequest,
    current_user: CurrentUser = Depends(_reviewer_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Accept the OCR text as-is. Emits OCR_ACCEPTED audit event."""
    db: AsyncSession = db_info["db"]
    try:
        result = await OcrReviewService.accept(
            queue_id, body.reviewer_notes, current_user,
            db=db, tenant_id=db_info["tenant_id"],
        )
    except OcrServiceError as e:
        _raise(e)
    await db.commit()
    return result


@router.post("/{queue_id}/correct", response_model=OcrActionResponse)
async def correct_ocr(
    queue_id: UUID,
    body: OcrCorrectRequest,
    current_user: CurrentUser = Depends(_reviewer_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Submit corrected OCR text. Emits OCR_TEXT_CORRECTED audit event."""
    db: AsyncSession = db_info["db"]
    try:
        result = await OcrReviewService.correct(
            queue_id, body.corrected_text, body.reviewer_notes, current_user,
            db=db, tenant_id=db_info["tenant_id"],
        )
    except OcrServiceError as e:
        _raise(e)
    await db.commit()
    return result


@router.post("/{queue_id}/rerun", response_model=OcrActionResponse)
async def request_rerun(
    queue_id: UUID,
    body: OcrRerunRequest,
    current_user: CurrentUser = Depends(_reviewer_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Request OCR re-extraction. Emits OCR_RERUN_REQUESTED audit event."""
    db: AsyncSession = db_info["db"]
    try:
        result = await OcrReviewService.request_rerun(
            queue_id, body.reviewer_notes, current_user,
            db=db, tenant_id=db_info["tenant_id"],
        )
    except OcrServiceError as e:
        _raise(e)
    await db.commit()
    return result


@router.post("/{queue_id}/escalate", response_model=OcrActionResponse)
async def escalate(
    queue_id: UUID,
    body: OcrEscalateRequest,
    current_user: CurrentUser = Depends(_reviewer_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Escalate to Admin. Emits OCR_ESCALATED audit event."""
    db: AsyncSession = db_info["db"]
    try:
        result = await OcrReviewService.escalate(
            queue_id, body.reviewer_notes, current_user,
            db=db, tenant_id=db_info["tenant_id"],
        )
    except OcrServiceError as e:
        _raise(e)
    await db.commit()
    return result


@router.post("/{queue_id}/unreadable", response_model=OcrActionResponse)
async def mark_unreadable(
    queue_id: UUID,
    body: OcrUnreadableRequest,
    current_user: CurrentUser = Depends(_reviewer_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Mark script as physically unreadable. Emits OCR_MARKED_UNREADABLE audit event."""
    db: AsyncSession = db_info["db"]
    try:
        result = await OcrReviewService.mark_unreadable(
            queue_id, body.reviewer_notes, current_user,
            db=db, tenant_id=db_info["tenant_id"],
        )
    except OcrServiceError as e:
        _raise(e)
    await db.commit()
    return result
