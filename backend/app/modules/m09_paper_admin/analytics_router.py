"""
M09.8 Examination Analytics — Router.

Mounted at /exam-analytics (see main.py).  Read-only analytics for Faculty,
Dean, Admin and the Examination Board.

RBAC
----
  _READ = ADMIN + DEAN + BOARD + FACULTY   cohort-level descriptive analytics
                                           (overview / subjects / grades / batches)
  _GOV  = ADMIN + DEAN + BOARD             governance-sensitive analytics
                                           (faculty marking patterns / moderation /
                                            revaluation) — excluded from FACULTY so
                                            one evaluator cannot inspect another's
                                            marking behaviour.

Every endpoint accepts an optional `exam_paper_id` query param: when present the
analytics are scoped to one paper, otherwise they are institution-wide.
`pass_threshold_pct` (default 40) is configurable per request for what-if views.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_context_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m09_paper_admin.analytics_schemas import (
    BatchAnalyticsResponse,
    DashboardResponse,
    FacultyAnalyticsResponse,
    GradeAnalyticsResponse,
    ModerationAnalyticsResponse,
    OcrAnalyticsResponse,
    OverviewResponse,
    RevaluationAnalyticsResponse,
    SubjectAnalyticsResponse,
)
from app.modules.m09_paper_admin.analytics_service import ExamAnalyticsService

router = APIRouter(tags=["M09.8 Examination Analytics"])

_READ = [TenantRole.ADMIN, TenantRole.DEAN, TenantRole.BOARD, TenantRole.FACULTY]
_GOV  = [TenantRole.ADMIN, TenantRole.DEAN, TenantRole.BOARD]


def _read_dep(): return require_roles(*_READ)
def _gov_dep():  return require_roles(*_GOV)


# ---------------------------------------------------------------------------
# Examination Overview
# ---------------------------------------------------------------------------

@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    exam_paper_id: UUID | None = Query(default=None),
    pass_threshold_pct: float = Query(default=40.0, ge=1.0, le=100.0),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Total / appeared / absent / pass / fail / pass% for a paper or institution."""
    db: AsyncSession = db_info["db"]
    return await ExamAnalyticsService.overview(
        exam_paper_id, pass_pct=pass_threshold_pct, db=db
    )


# ---------------------------------------------------------------------------
# Subject Analytics
# ---------------------------------------------------------------------------

@router.get("/subjects", response_model=SubjectAnalyticsResponse)
async def get_subjects(
    exam_paper_id: UUID | None = Query(default=None),
    pass_threshold_pct: float = Query(default=40.0, ge=1.0, le=100.0),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Per-subject average / median / high / low / pass% (hardest subjects first)."""
    db: AsyncSession = db_info["db"]
    return await ExamAnalyticsService.subjects(
        exam_paper_id, pass_pct=pass_threshold_pct, db=db
    )


# ---------------------------------------------------------------------------
# Grade Distribution
# ---------------------------------------------------------------------------

@router.get("/grades", response_model=GradeAnalyticsResponse)
async def get_grades(
    exam_paper_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Histogram-ready grade buckets (A+ … F)."""
    db: AsyncSession = db_info["db"]
    return await ExamAnalyticsService.grades(exam_paper_id, db=db)


# ---------------------------------------------------------------------------
# Batch Analytics
# ---------------------------------------------------------------------------

@router.get("/batches", response_model=BatchAnalyticsResponse)
async def get_batches(
    exam_paper_id: UUID | None = Query(default=None),
    pass_threshold_pct: float = Query(default=40.0, ge=1.0, le=100.0),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Per-admission-year (batch) pass% / average / topper."""
    db: AsyncSession = db_info["db"]
    return await ExamAnalyticsService.batches(
        exam_paper_id, pass_pct=pass_threshold_pct, db=db
    )


# ---------------------------------------------------------------------------
# Faculty Analytics (governance-sensitive)
# ---------------------------------------------------------------------------

@router.get("/faculty", response_model=FacultyAnalyticsResponse)
async def get_faculty(
    exam_paper_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(_gov_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Per-evaluator scripts evaluated / avg awarded / turnaround, vs institution benchmark."""
    db: AsyncSession = db_info["db"]
    return await ExamAnalyticsService.faculty(exam_paper_id, db=db)


# ---------------------------------------------------------------------------
# Revaluation Analytics (governance-sensitive)
# ---------------------------------------------------------------------------

@router.get("/revaluation", response_model=RevaluationAnalyticsResponse)
async def get_revaluation(
    exam_paper_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(_gov_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Revaluation requests: increased / unchanged / average increase."""
    db: AsyncSession = db_info["db"]
    return await ExamAnalyticsService.revaluation(exam_paper_id, db=db)


# ---------------------------------------------------------------------------
# Moderation Analytics (governance-sensitive)
# ---------------------------------------------------------------------------

@router.get("/moderation", response_model=ModerationAnalyticsResponse)
async def get_moderation(
    exam_paper_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(_gov_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Moderation events: scripts moderated / average variance / average correction delta."""
    db: AsyncSession = db_info["db"]
    return await ExamAnalyticsService.moderation(exam_paper_id, db=db)


# ---------------------------------------------------------------------------
# Dashboard bundle
# ---------------------------------------------------------------------------

@router.get("/ocr", response_model=OcrAnalyticsResponse)
async def get_ocr_analytics(
    exam_paper_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(_gov_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """OCR accuracy rate, average confidence, corrections per reviewer, quality distribution."""
    db: AsyncSession = db_info["db"]
    return await ExamAnalyticsService.ocr_analytics(exam_paper_id, db=db)


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    exam_paper_id: UUID | None = Query(default=None),
    pass_threshold_pct: float = Query(default=40.0, ge=1.0, le=100.0),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """One-shot landing bundle: overview + grades + hardest subjects + reval + moderation."""
    db: AsyncSession = db_info["db"]
    return await ExamAnalyticsService.dashboard(
        exam_paper_id, pass_pct=pass_threshold_pct, db=db
    )
