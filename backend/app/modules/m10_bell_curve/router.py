"""
M10 Bell Curve Normaliser — Router.

RBAC
----
  _BOARD_ADMIN = BOARD + ADMIN         (trigger, ratify, ledger, decisions)
  _READ        = BOARD + ADMIN + DEAN  (view analyses, decisions, reports)

Route summary
-------------
  POST   /bell-curve/analyses                        trigger analysis for an exam paper
  GET    /bell-curve/analyses                        list all analyses (paginated)
  GET    /bell-curve/analyses/{id}                   analysis detail
  GET    /bell-curve/analyses/paper/{paper_id}       analyses for one paper
  GET    /bell-curve/analyses/{id}/job               Celery job status poll
  POST   /bell-curve/analyses/{id}/preview           preview normalisation (no DB write)
  POST   /bell-curve/analyses/{id}/ratify            Gate 1: Board ratifies
  GET    /bell-curve/decisions                       list all Board decisions
  GET    /bell-curve/decisions/{id}                  decision detail
  GET    /bell-curve/ledger/paper/{paper_id}         normalised scores for a paper
  GET    /bell-curve/reports/semester                fairness PDF report (StreamingResponse)

Static paths (/analyses/paper/..., /decisions/{id}, /ledger/..., /reports/...)
are declared before /{id} patterns so FastAPI routes them as literals.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_context_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m10_bell_curve.schemas import (
    BellCurveAnalysisListResponse,
    BellCurveAnalysisResponse,
    BellCurveDecisionListResponse,
    BellCurveDecisionResponse,
    NormalisedScoreListResponse,
    NormalisedScoreResponse,
    PreviewNormalisationRequest,
    PreviewNormalisationResponse,
    RatifyRequest,
    RatifyResponse,
    TriggerAnalysisRequest,
    TriggerAnalysisResponse,
)
from app.modules.m10_bell_curve.grade_engine import compute_grade as _compute_grade
from app.modules.m10_bell_curve.service import BellCurveService, BellCurveServiceError

router = APIRouter(tags=["M10 Bell Curve"])


def _to_score_response(orm_obj) -> NormalisedScoreResponse:
    """Enrich a normalised-score ORM row with computed grade fields."""
    resp = NormalisedScoreResponse.model_validate(orm_obj)
    pct, letter, points, passed = _compute_grade(resp.normalised_score, resp.max_marks)
    resp.pct          = pct
    resp.grade_letter = letter
    resp.grade_point  = points
    resp.is_pass      = passed
    return resp

# ---------------------------------------------------------------------------
# Role groups
# ---------------------------------------------------------------------------

_BOARD_ADMIN = [TenantRole.BOARD, TenantRole.ADMIN]
_READ        = [TenantRole.BOARD, TenantRole.ADMIN, TenantRole.DEAN]


def _board_admin_dep(): return require_roles(*_BOARD_ADMIN)
def _read_dep():        return require_roles(*_READ)


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------

def _raise(exc: BellCurveServiceError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "message": exc.message},
    )


# ---------------------------------------------------------------------------
# POST /analyses — trigger analysis
# ---------------------------------------------------------------------------

@router.post("/analyses", response_model=TriggerAnalysisResponse, status_code=202)
async def trigger_analysis(
    payload:      TriggerAnalysisRequest,
    current_user: CurrentUser = Depends(_board_admin_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Trigger bell curve analysis for an exam paper.
    All scanned_scripts for the paper must be BOARD_FINALISED (409 if not).
    Returns 202 Accepted with analysis_id and job_id for polling.
    """
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        analysis, job_id = await BellCurveService.trigger(
            exam_paper_id = payload.exam_paper_id,
            triggered_by  = current_user.user_id,
            tenant_id     = tenant_id,
            schema_name   = schema,
            db            = db,
        )
    except BellCurveServiceError as exc:
        _raise(exc)

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    await AuditService.log(
        AuditEventType.BELL_CURVE_ANALYSIS_TRIGGERED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="bell_curve_analysis",
        target_id=str(analysis.id),
        metadata={"exam_paper_id": str(payload.exam_paper_id), "job_id": str(job_id)},
    )

    return TriggerAnalysisResponse(
        analysis_id=analysis.id,
        job_id=job_id,
        status=analysis.status,
    )


# ---------------------------------------------------------------------------
# GET /analyses/paper/{paper_id} — STATIC (must be before /{id})
# ---------------------------------------------------------------------------

@router.get("/analyses/paper/{paper_id}", response_model=BellCurveAnalysisListResponse)
async def list_analyses_for_paper(
    paper_id: UUID,
    offset:   int = Query(default=0, ge=0),
    limit:    int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """List all analyses for a specific exam paper."""
    db: AsyncSession = db_info["db"]
    items, total = await BellCurveService.list_for_paper(paper_id, offset, limit, db=db)
    return BellCurveAnalysisListResponse(
        items=[BellCurveAnalysisResponse.model_validate(a) for a in items],
        total=total, offset=offset, limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /analyses — list all
# ---------------------------------------------------------------------------

@router.get("/analyses", response_model=BellCurveAnalysisListResponse)
async def list_analyses(
    offset: int = Query(default=0, ge=0),
    limit:  int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """List all bell curve analyses for the tenant."""
    db: AsyncSession = db_info["db"]
    items, total = await BellCurveService.list_all(offset, limit, db=db)
    return BellCurveAnalysisListResponse(
        items=[BellCurveAnalysisResponse.model_validate(a) for a in items],
        total=total, offset=offset, limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /analyses/{id} — detail
# ---------------------------------------------------------------------------

@router.get("/analyses/{analysis_id}", response_model=BellCurveAnalysisResponse)
async def get_analysis(
    analysis_id:  UUID,
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Get analysis detail including stats, anomalies, and suggestion."""
    db: AsyncSession = db_info["db"]
    try:
        analysis = await BellCurveService.get(analysis_id, db=db)
    except BellCurveServiceError as exc:
        _raise(exc)
    return BellCurveAnalysisResponse.model_validate(analysis)


# ---------------------------------------------------------------------------
# GET /analyses/{id}/job — Celery job status
# ---------------------------------------------------------------------------

@router.get("/analyses/{analysis_id}/job")
async def get_analysis_job_status(
    analysis_id:  UUID,
    current_user: CurrentUser = Depends(_board_admin_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Poll the Celery task_job status for an analysis."""
    db: AsyncSession = db_info["db"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        analysis = await BellCurveService.get(analysis_id, db=db)
    except BellCurveServiceError as exc:
        _raise(exc)

    if analysis.analysis_job_id is None:
        return {"analysis_id": str(analysis_id), "job_id": None, "status": "UNKNOWN"}

    from app.database import async_session_public
    from app.modules.m10_bell_curve.repository import TaskJobPublicRepository
    async with async_session_public() as pub_db:
        job = await TaskJobPublicRepository.get_by_id(
            analysis.analysis_job_id, tenant_id=tenant_id, db=pub_db
        )

    if job is None:
        return {"analysis_id": str(analysis_id), "job_id": str(analysis.analysis_job_id), "status": "UNKNOWN"}

    return {
        "analysis_id":  str(analysis_id),
        "job_id":       str(job["id"]),
        "status":       job["status"],
        "started_at":   job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "error":        job.get("error"),
    }


# ---------------------------------------------------------------------------
# POST /analyses/{id}/preview — no DB write
# ---------------------------------------------------------------------------

@router.post("/analyses/{analysis_id}/preview", response_model=PreviewNormalisationResponse)
async def preview_normalisation(
    analysis_id:  UUID,
    payload:      PreviewNormalisationRequest,
    current_user: CurrentUser = Depends(_board_admin_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Preview normalisation with custom params.
    Computes projected distribution in-memory — NO database write.
    """
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        result = await BellCurveService.preview(
            analysis_id=analysis_id,
            method=payload.method.value,
            params=payload.params,
            db=db,
        )
    except BellCurveServiceError as exc:
        _raise(exc)

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    await AuditService.log(
        AuditEventType.BELL_CURVE_NORMALISATION_PREVIEWED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="bell_curve_analysis",
        target_id=str(analysis_id),
        metadata={"method": payload.method.value, "params": payload.params},
    )

    from app.modules.m10_bell_curve.models import NormalisationMethod
    return PreviewNormalisationResponse(
        method          = NormalisationMethod(result["method"]),
        params          = result["params"],
        projected_stats = result["projected_stats"],
        score_deltas    = result["score_deltas"],
    )


# ---------------------------------------------------------------------------
# POST /analyses/{id}/ratify — Gate 1 (BOARD only)
# ---------------------------------------------------------------------------

@router.post("/analyses/{analysis_id}/ratify", response_model=RatifyResponse)
async def ratify_analysis(
    analysis_id:  UUID,
    payload:      RatifyRequest,
    current_user: CurrentUser = Depends(require_roles(TenantRole.BOARD)),
    db_info=Depends(get_tenant_context_dep),
):
    """
    GATE 1: Board member ratifies the normalisation decision.
    Writes bell_curve_decisions and (if not REJECTED) bell_curve_normalized_scores.
    exam_score_ledger is NEVER modified.
    """
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        analysis, decision_obj, scores_written = await BellCurveService.ratify(
            analysis_id          = analysis_id,
            decision             = payload.decision.value,
            normalisation_method = payload.normalisation_method.value,
            normalisation_params = payload.normalisation_params,
            ratification_note    = payload.ratification_note,
            ratified_by          = current_user.user_id,
            tenant_id            = tenant_id,
            schema_name          = schema,
            db                   = db,
        )
    except BellCurveServiceError as exc:
        _raise(exc)

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    await AuditService.log(
        AuditEventType.BELL_CURVE_BOARD_RATIFIED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="bell_curve_analysis",
        target_id=str(analysis_id),
        metadata={
            "decision":       payload.decision.value,
            "method":         payload.normalisation_method.value,
            "params":         payload.normalisation_params,
            "scores_written": scores_written,
            "decision_id":    str(decision_obj.id),
        },
    )

    return RatifyResponse(
        analysis_id   = analysis_id,
        decision_id   = decision_obj.id,
        decision      = payload.decision,
        method        = payload.normalisation_method,
        scores_written = scores_written,
    )


# ---------------------------------------------------------------------------
# GET /decisions — list all decisions
# ---------------------------------------------------------------------------

@router.get("/decisions", response_model=BellCurveDecisionListResponse)
async def list_decisions(
    offset: int = Query(default=0, ge=0),
    limit:  int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(_board_admin_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """List all Board ratification decisions."""
    db: AsyncSession = db_info["db"]
    items, total = await BellCurveService.list_decisions(offset, limit, db=db)
    return BellCurveDecisionListResponse(
        items=[BellCurveDecisionResponse.model_validate(d) for d in items],
        total=total, offset=offset, limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /decisions/{id} — decision detail
# ---------------------------------------------------------------------------

@router.get("/decisions/{decision_id}", response_model=BellCurveDecisionResponse)
async def get_decision(
    decision_id:  UUID,
    current_user: CurrentUser = Depends(_board_admin_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Get a Board ratification decision."""
    db: AsyncSession = db_info["db"]
    try:
        decision = await BellCurveService.get_decision(decision_id, db=db)
    except BellCurveServiceError as exc:
        _raise(exc)
    return BellCurveDecisionResponse.model_validate(decision)


# ---------------------------------------------------------------------------
# GET /ledger/paper/{paper_id} — normalised scores for a paper
# ---------------------------------------------------------------------------

@router.get("/ledger/paper/{paper_id}", response_model=NormalisedScoreListResponse)
async def list_normalised_ledger(
    paper_id: UUID,
    offset:   int = Query(default=0, ge=0),
    limit:    int = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(_board_admin_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """List Board-ratified normalised score records for an exam paper."""
    db: AsyncSession = db_info["db"]
    items, total = await BellCurveService.list_ledger_for_paper(
        paper_id, offset, limit, db=db
    )
    return NormalisedScoreListResponse(
        items=[_to_score_response(s) for s in items],
        total=total, offset=offset, limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /reports/semester — fairness PDF report (synchronous StreamingResponse)
# ---------------------------------------------------------------------------

@router.get("/reports/semester")
async def fairness_report(
    exam_paper_id: UUID | None = Query(default=None, description="Filter by exam paper"),
    current_user:  CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Generate a Bell Curve Fairness Report as a PDF.
    Data is pre-computed in bell_curve_analyses + bell_curve_decisions.
    Report is generated synchronously using reportlab.
    Audit logs: BELL_CURVE_REPORT_EXPORTED.
    """
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    # Gather data for report
    if exam_paper_id:
        analyses, _total = await BellCurveService.list_for_paper(
            exam_paper_id, offset=0, limit=200, db=db
        )
    else:
        analyses, _total = await BellCurveService.list_all(offset=0, limit=200, db=db)

    decisions_map: dict = {}
    for analysis in analyses:
        from app.modules.m10_bell_curve.repository import BellCurveDecisionRepository
        dec = await BellCurveDecisionRepository.get_for_analysis(analysis.id, db=db)
        if dec:
            decisions_map[str(analysis.id)] = dec

    from app.modules.m10_bell_curve.report_builder import generate_fairness_pdf
    import io
    buf = io.BytesIO()
    generate_fairness_pdf(buf, analyses=analyses, decisions_map=decisions_map)
    buf.seek(0)

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    await AuditService.log(
        AuditEventType.BELL_CURVE_REPORT_EXPORTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="bell_curve_report",
        target_id=str(exam_paper_id) if exam_paper_id else "all",
        metadata={"analyses_count": len(analyses)},
    )

    filename = f"bell_curve_fairness_report.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
