"""
M09.9 Compliance & Audit — Router.

Mounted at /exam-compliance (see main.py).  Examination governance: complete,
immutable audit trails plus compliance report exports.

RBAC
----
  _GOV = ADMIN + DEAN + BOARD   — all compliance views are governance-sensitive
                                  and therefore excluded from FACULTY, so one
                                  evaluator can never inspect the audit trail of
                                  another evaluator or of a student.

Every endpoint is read-only.  The only write in the whole subsystem is the
internal, append-only mark-audit recorder driven by the evaluation service.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_context_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m09_paper_admin.compliance_schemas import (
    AuditTrailResponse,
    ComplianceDashboardResponse,
    ReportResponse,
    ResultChangeHistoryResponse,
)
from app.modules.m09_paper_admin.compliance_service import ComplianceService

router = APIRouter(tags=["M09.9 Compliance & Audit"])

_GOV = [TenantRole.ADMIN, TenantRole.DEAN, TenantRole.BOARD]


def _gov_dep():
    return require_roles(*_GOV)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=ComplianceDashboardResponse)
async def get_dashboard(
    exam_paper_id: UUID | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    current_user: CurrentUser = Depends(_gov_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """KPI bundle + category breakdown + recent governance events."""
    db: AsyncSession = db_info["db"]
    return await ComplianceService.dashboard(
        exam_paper_id, tenant_id=db_info["tenant_id"],
        date_from=date_from, date_to=date_to, db=db,
    )


# ---------------------------------------------------------------------------
# Audit trails (by student / script / exam / evaluator / date range)
# ---------------------------------------------------------------------------

@router.get("/audit-trail/student/{student_user_id}", response_model=AuditTrailResponse)
async def trail_by_student(
    student_user_id: UUID,
    category: list[str] | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_gov_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    db: AsyncSession = db_info["db"]
    return await ComplianceService.trail_by_student(
        student_user_id, tenant_id=db_info["tenant_id"], categories=category,
        date_from=date_from, date_to=date_to, page=page, page_size=page_size, db=db,
    )


@router.get("/audit-trail/script/{script_id}", response_model=AuditTrailResponse)
async def trail_by_script(
    script_id: UUID,
    category: list[str] | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_gov_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    db: AsyncSession = db_info["db"]
    return await ComplianceService.trail_by_script(
        script_id, tenant_id=db_info["tenant_id"], categories=category,
        date_from=date_from, date_to=date_to, page=page, page_size=page_size, db=db,
    )


@router.get("/audit-trail/exam/{exam_paper_id}", response_model=AuditTrailResponse)
async def trail_by_exam(
    exam_paper_id: UUID,
    category: list[str] | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_gov_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    db: AsyncSession = db_info["db"]
    return await ComplianceService.trail_by_exam(
        exam_paper_id, tenant_id=db_info["tenant_id"], categories=category,
        date_from=date_from, date_to=date_to, page=page, page_size=page_size, db=db,
    )


@router.get("/audit-trail/evaluator/{evaluator_id}", response_model=AuditTrailResponse)
async def trail_by_evaluator(
    evaluator_id: UUID,
    category: list[str] | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_gov_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    db: AsyncSession = db_info["db"]
    return await ComplianceService.trail_by_evaluator(
        evaluator_id, tenant_id=db_info["tenant_id"], categories=category,
        date_from=date_from, date_to=date_to, page=page, page_size=page_size, db=db,
    )


@router.get("/audit-trail", response_model=AuditTrailResponse)
async def trail_by_date_range(
    category: list[str] | None = Query(default=None),
    actor_user_id: UUID | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_gov_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Institution-wide governance trail, filterable by date range, category and actor."""
    db: AsyncSession = db_info["db"]
    return await ComplianceService.trail_by_date_range(
        tenant_id=db_info["tenant_id"], categories=category, actor_user_id=actor_user_id,
        date_from=date_from, date_to=date_to, page=page, page_size=page_size, db=db,
    )


# ---------------------------------------------------------------------------
# Result change history (drill-down for one script)
# ---------------------------------------------------------------------------

@router.get("/result-history/{script_id}", response_model=ResultChangeHistoryResponse)
async def result_change_history(
    script_id: UUID,
    current_user: CurrentUser = Depends(_gov_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Field-level recorded mark changes + derived per-question value lineage."""
    db: AsyncSession = db_info["db"]
    return await ComplianceService.result_change_history(script_id, db=db)


# ---------------------------------------------------------------------------
# Compliance reports (JSON + CSV export)
# ---------------------------------------------------------------------------

@router.get("/reports", response_model=list[str])
async def list_reports(
    current_user: CurrentUser = Depends(_gov_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    return ComplianceService.report_names()


@router.get("/reports/{report}", response_model=ReportResponse)
async def get_report(
    report: str,
    exam_paper_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(_gov_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    if report not in ComplianceService.report_names():
        raise HTTPException(status_code=404, detail=f"Unknown report '{report}'.")
    db: AsyncSession = db_info["db"]
    return await ComplianceService.run_report(report, exam_paper_id, db=db)


@router.get("/reports/{report}/export")
async def export_report_csv(
    report: str,
    exam_paper_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(_gov_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Download a compliance report as a CSV attachment."""
    if report not in ComplianceService.report_names():
        raise HTTPException(status_code=404, detail=f"Unknown report '{report}'.")
    db: AsyncSession = db_info["db"]
    csv_text = await ComplianceService.run_report_csv(report, exam_paper_id, db=db)
    filename = f"compliance_{report}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
