"""
SIS Graduation Audit — H62 Router.

Route ordering rule: literal paths BEFORE parameterized paths.

Tenant routes (under /sis/graduation/...):
  GET    /graduation/my-graduation-status          — Student (literal — must be first)
  POST   /graduation/audits/trigger                — Dean/Admin
  GET    /graduation/audits                        — Dean/Admin/Board
  GET    /graduation/audits/{audit_id}             — Dean/Admin/Board
  POST   /graduation/audits/{audit_id}/regenerate  — Dean/Admin
  POST   /graduation/audits/{audit_id}/submit      — Dean/Admin
  POST   /graduation/audits/{audit_id}/approve     — Board/Dean
  POST   /graduation/audits/{audit_id}/issue-all   — Admin/Dean
  GET    /graduation/audits/{audit_id}/candidates  — Dean/Admin/Board
  GET    /graduation/audits/{audit_id}/report-url  — Dean/Admin/Board
  POST   /graduation/candidates/{id}/ratify        — Board/Dean
  POST   /graduation/candidates/{id}/defer         — Board/Dean
  POST   /graduation/candidates/{id}/override      — Dean/Admin
  GET    /graduation/candidates/{id}               — Dean/Admin/Board
  POST   /graduation/certificates/{id}/issue       — Admin/Dean
  GET    /graduation/certificates                  — Admin/Dean/Board
  GET    /graduation/certificates/{id}             — Admin/Dean/Board
  POST   /graduation/certificates/{id}/confirm-provisional — Admin/Dean
  POST   /graduation/certificates/{id}/revoke      — Admin/Dean

Platform verify route (no tenant prefix, no auth):
  GET    /verify/certificate/{certificate_number}
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.graduation_schemas import (
    AuditApproveIn,
    AuditReportDispatchResponse,
    BoardDeferIn,
    BoardRatifyIn,
    CandidateOverrideIn,
    CertificateRevokeIn,
    CertificateVerifyResponse,
    GraduationAuditCreate,
    GraduationAuditDetailRead,
    GraduationAuditSummaryRead,
    GraduationCandidateDetailRead,
    GraduationCandidateSummaryRead,
    GraduationCertificateRead,
    ProvisionalConfirmIn,
    StudentGraduationStatusRead,
)
from app.modules.m11_sis.graduation_service import (
    GraduationLifecycleService,
    GraduationVerifyService,
    StudentGraduationService,
)

_ADMIN    = [TenantRole.ADMIN]
_DEAN     = [TenantRole.DEAN]
_BOARD    = [TenantRole.BOARD, TenantRole.DEAN]
_MANAGERS = [TenantRole.ADMIN, TenantRole.DEAN]
_ALL_STAFF = [TenantRole.ADMIN, TenantRole.DEAN, TenantRole.BOARD]
_STUDENT  = [TenantRole.STUDENT]


async def _tenant_code(current_user: CurrentUser, db: AsyncSession) -> str:
    """Resolve tenant short code (slug) for certificate numbering."""
    t_row = (await db.execute(
        text("SELECT slug FROM public.tenants WHERE id = :tid"),
        {"tid": str(current_user.tenant_id)},
    )).mappings().one_or_none()
    return (t_row["slug"] if t_row else "UNK").upper().replace("-", "")[:8]


graduation_router = APIRouter(prefix="/graduation", tags=["SIS Graduation"])


# ─────────────────────────────────────────────────────────────────────────────
# LITERAL student route — MUST come before parameterized /{audit_id} routes
# ─────────────────────────────────────────────────────────────────────────────

@graduation_router.get(
    "/my-graduation-status",
    response_model=StudentGraduationStatusRead,
    summary="Student: view own graduation status",
)
async def get_my_graduation_status(
    current_user: CurrentUser = Depends(require_roles(*_STUDENT)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    return await StudentGraduationService.my_status(current_user.user_id, db)


# ─────────────────────────────────────────────────────────────────────────────
# Audit endpoints
# ─────────────────────────────────────────────────────────────────────────────

@graduation_router.post(
    "/audits/trigger",
    response_model=GraduationAuditSummaryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger a new graduation audit for a batch",
)
async def trigger_audit(
    body:         GraduationAuditCreate,
    current_user: CurrentUser  = Depends(require_roles(*_MANAGERS)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        audit = await GraduationLifecycleService.trigger(body.batch_id, current_user, db)
        await db.commit()
        return GraduationAuditSummaryRead.model_validate(audit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@graduation_router.get(
    "/audits",
    response_model=list[GraduationAuditSummaryRead],
    summary="List graduation audits",
)
async def list_audits(
    status_filter: str | None  = Query(None, alias="status"),
    batch_id:      UUID | None = Query(None),
    offset:        int          = Query(0, ge=0),
    limit:         int          = Query(50, ge=1, le=200),
    current_user: CurrentUser  = Depends(require_roles(*_ALL_STAFF)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    from app.modules.m11_sis.graduation_repository import GraduationAuditRepo
    items = await GraduationAuditRepo.list_all(
        db,
        status_filter=status_filter,
        batch_id=batch_id,
        offset=offset,
        limit=limit,
    )
    return [GraduationAuditSummaryRead.model_validate(a) for a in items]


@graduation_router.get(
    "/audits/{audit_id}",
    response_model=GraduationAuditDetailRead,
    summary="Get full graduation audit details with candidate list",
)
async def get_audit(
    audit_id:     UUID,
    current_user: CurrentUser  = Depends(require_roles(*_ALL_STAFF)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    from app.modules.m11_sis.graduation_repository import GraduationAuditRepo
    audit = await GraduationAuditRepo.get_by_id(audit_id, db, with_candidates=True)
    if not audit:
        raise HTTPException(status_code=404, detail="Graduation audit not found")
    return GraduationAuditDetailRead.model_validate(audit)


@graduation_router.post(
    "/audits/{audit_id}/regenerate",
    response_model=GraduationAuditSummaryRead,
    summary="Regenerate eligibility data for a DRAFT audit",
)
async def regenerate_audit(
    audit_id:     UUID,
    current_user: CurrentUser  = Depends(require_roles(*_MANAGERS)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        audit = await GraduationLifecycleService.regenerate(audit_id, current_user, db)
        await db.commit()
        return GraduationAuditSummaryRead.model_validate(audit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@graduation_router.post(
    "/audits/{audit_id}/submit",
    response_model=GraduationAuditSummaryRead,
    summary="Gate 1: Dean submits audit for Board review",
)
async def submit_audit(
    audit_id:     UUID,
    current_user: CurrentUser  = Depends(require_roles(*(_DEAN + _ADMIN))),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        audit = await GraduationLifecycleService.submit(audit_id, current_user, db)
        await db.commit()
        return GraduationAuditSummaryRead.model_validate(audit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@graduation_router.post(
    "/audits/{audit_id}/approve",
    response_model=GraduationAuditSummaryRead,
    summary="Gate 2b: Board approves audit batch (board_resolution_ref required)",
)
async def approve_audit(
    audit_id:     UUID,
    body:         AuditApproveIn,
    current_user: CurrentUser  = Depends(require_roles(*_BOARD)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        audit = await GraduationLifecycleService.approve(audit_id, body, current_user, db)
        await db.commit()
        return GraduationAuditSummaryRead.model_validate(audit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@graduation_router.post(
    "/audits/{audit_id}/issue-all",
    response_model=list[GraduationCertificateRead],
    status_code=status.HTTP_201_CREATED,
    summary="Gate 3: Issue certificates for all ratified candidates in a BOARD_APPROVED audit",
)
async def issue_all_certificates(
    audit_id:     UUID,
    current_user: CurrentUser  = Depends(require_roles(*_MANAGERS)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    tc = await _tenant_code(current_user, db)
    try:
        certs = await GraduationLifecycleService.issue_all_certificates(
            audit_id, current_user, tc, db
        )
        await db.commit()
        return [GraduationCertificateRead.model_validate(c) for c in certs]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@graduation_router.get(
    "/audits/{audit_id}/candidates",
    response_model=list[GraduationCandidateSummaryRead],
    summary="List candidates for an audit",
)
async def list_audit_candidates(
    audit_id:          UUID,
    eligibility_filter: str | None = Query(None, alias="eligibility_status"),
    board_filter:       str | None = Query(None, alias="board_status"),
    offset:             int         = Query(0, ge=0),
    limit:              int         = Query(100, ge=1, le=500),
    current_user: CurrentUser  = Depends(require_roles(*_ALL_STAFF)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    from app.modules.m11_sis.graduation_repository import GraduationCandidateRepo
    items = await GraduationCandidateRepo.list_for_audit(
        audit_id, db,
        eligibility_filter=eligibility_filter,
        board_filter=board_filter,
        offset=offset,
        limit=limit,
    )
    return [GraduationCandidateSummaryRead.model_validate(c) for c in items]


@graduation_router.get(
    "/audits/{audit_id}/report-url",
    response_model=AuditReportDispatchResponse,
    summary="Dispatch Celery task to generate audit report PDF",
)
async def get_audit_report_url(
    audit_id:     UUID,
    current_user: CurrentUser  = Depends(require_roles(*_ALL_STAFF)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    from app.workers.heavy.generate_graduation_report import generate_graduation_report
    task = generate_graduation_report.delay(str(audit_id))
    return AuditReportDispatchResponse(
        audit_id=audit_id,
        celery_task_id=task.id,
        message="Audit report generation queued. Poll /tasks/{task_id} for status.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Candidate endpoints
# ─────────────────────────────────────────────────────────────────────────────

@graduation_router.post(
    "/candidates/{candidate_id}/ratify",
    response_model=GraduationCandidateDetailRead,
    summary="Gate 2a: Board ratifies a candidate",
)
async def ratify_candidate(
    candidate_id: UUID,
    body:         BoardRatifyIn,
    current_user: CurrentUser  = Depends(require_roles(*_BOARD)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        candidate = await GraduationLifecycleService.ratify_candidate(
            candidate_id, body, current_user, db
        )
        await db.commit()
        return GraduationCandidateDetailRead.model_validate(candidate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@graduation_router.post(
    "/candidates/{candidate_id}/defer",
    response_model=GraduationCandidateDetailRead,
    summary="Gate 2a: Board defers a candidate",
)
async def defer_candidate(
    candidate_id: UUID,
    body:         BoardDeferIn,
    current_user: CurrentUser  = Depends(require_roles(*_BOARD)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        candidate = await GraduationLifecycleService.defer_candidate(
            candidate_id, body, current_user, db
        )
        await db.commit()
        return GraduationCandidateDetailRead.model_validate(candidate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@graduation_router.post(
    "/candidates/{candidate_id}/override",
    response_model=GraduationCandidateDetailRead,
    summary="Dean overrides candidate eligibility status",
)
async def override_candidate(
    candidate_id: UUID,
    body:         CandidateOverrideIn,
    current_user: CurrentUser  = Depends(require_roles(*_MANAGERS)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        candidate = await GraduationLifecycleService.override_candidate(
            candidate_id, body, current_user, db
        )
        await db.commit()
        return GraduationCandidateDetailRead.model_validate(candidate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@graduation_router.get(
    "/candidates/{candidate_id}",
    response_model=GraduationCandidateDetailRead,
    summary="Get candidate detail (includes eligibility flags and board notes)",
)
async def get_candidate(
    candidate_id: UUID,
    current_user: CurrentUser  = Depends(require_roles(*_ALL_STAFF)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    from app.modules.m11_sis.graduation_repository import GraduationCandidateRepo
    candidate = await GraduationCandidateRepo.get_by_id(candidate_id, db)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return GraduationCandidateDetailRead.model_validate(candidate)


# ─────────────────────────────────────────────────────────────────────────────
# Certificate endpoints
# ─────────────────────────────────────────────────────────────────────────────

@graduation_router.post(
    "/certificates/{candidate_id}/issue",
    response_model=GraduationCertificateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Gate 3: Issue certificate for a single ratified candidate",
)
async def issue_single_certificate(
    candidate_id: UUID,
    current_user: CurrentUser  = Depends(require_roles(*_MANAGERS)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    tc = await _tenant_code(current_user, db)
    try:
        cert = await GraduationLifecycleService.issue_certificate(
            candidate_id, current_user, tc, db
        )
        await db.commit()
        return GraduationCertificateRead.model_validate(cert)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@graduation_router.get(
    "/certificates",
    response_model=list[GraduationCertificateRead],
    summary="List issued graduation certificates",
)
async def list_certificates(
    status_filter: str | None  = Query(None, alias="status"),
    student_id:    UUID | None = Query(None),
    offset:        int          = Query(0, ge=0),
    limit:         int          = Query(50, ge=1, le=200),
    current_user: CurrentUser  = Depends(require_roles(*(_MANAGERS + [TenantRole.BOARD]))),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    from app.modules.m11_sis.graduation_repository import GraduationCertificateRepo
    items = await GraduationCertificateRepo.list_all(
        db,
        status_filter=status_filter,
        student_id=student_id,
        offset=offset,
        limit=limit,
    )
    return [GraduationCertificateRead.model_validate(c) for c in items]


@graduation_router.get(
    "/certificates/{cert_id}",
    response_model=GraduationCertificateRead,
    summary="Get graduation certificate details",
)
async def get_certificate(
    cert_id:      UUID,
    current_user: CurrentUser  = Depends(require_roles(*(_MANAGERS + [TenantRole.BOARD]))),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    from app.modules.m11_sis.graduation_repository import GraduationCertificateRepo
    cert = await GraduationCertificateRepo.get_by_id(cert_id, db)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return GraduationCertificateRead.model_validate(cert)


@graduation_router.post(
    "/certificates/{cert_id}/confirm-provisional",
    response_model=GraduationCertificateRead,
    summary="Confirm provisional graduation → full graduation",
)
async def confirm_provisional(
    cert_id:      UUID,
    body:         ProvisionalConfirmIn,
    current_user: CurrentUser  = Depends(require_roles(*_MANAGERS)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        cert = await GraduationLifecycleService.confirm_provisional(
            cert_id, body, current_user, db
        )
        await db.commit()
        return GraduationCertificateRead.model_validate(cert)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@graduation_router.post(
    "/certificates/{cert_id}/revoke",
    response_model=GraduationCertificateRead,
    summary="Revoke a graduation certificate (GRADUATION_REVOKED)",
)
async def revoke_certificate(
    cert_id:      UUID,
    body:         CertificateRevokeIn,
    current_user: CurrentUser  = Depends(require_roles(*_MANAGERS)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        cert = await GraduationLifecycleService.revoke_certificate(
            cert_id, body, current_user, db
        )
        await db.commit()
        return GraduationCertificateRead.model_validate(cert)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Public certificate verification — no tenant prefix, no auth
# Full path is /verify/certificate/{certificate_number}
# Mounted in main.py as: app.include_router(cert_verify_router)  (no prefix)
# ─────────────────────────────────────────────────────────────────────────────

cert_verify_router = APIRouter(tags=["Public Certificate Verification"])


@cert_verify_router.get(
    "/verify/certificate/{certificate_number}",
    response_model=CertificateVerifyResponse,
    summary="Public: verify a graduation certificate by number",
)
async def verify_certificate(
    certificate_number: str,
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    return await GraduationVerifyService.verify(certificate_number, db)
