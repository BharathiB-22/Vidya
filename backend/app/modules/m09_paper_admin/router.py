"""
M09 Paper Administration & Scanning — Router.

RBAC
----
  _INGEST   = ADMIN + BOARD           (upload / assign evaluator)
  _EVALUATE = ADMIN + (FACULTY role OR active FACULTY grant)   (update marks / Gate 1 submit)
  _BOARD    = BOARD + ADMIN           (Gate 2 finalise / ledger read)
  _READ     = all tenant roles        (script detail / evaluations / list)

Route summary
-------------
  POST   /scripts/upload                       ingest scanned script + queue scoring
  GET    /scripts                              list all scripts (ADMIN/BOARD)
  GET    /scripts/board/pending                scripts awaiting Board finalisation
  GET    /scripts/evaluator/me                 evaluator's own assigned scripts
  GET    /scripts/paper/{paper_id}             scripts for an exam paper
  GET    /scripts/stats                        pipeline-status counts for a paper (H-36)
  GET    /scripts/{script_id}                  script detail (identity masked pre-finalise)
  POST   /scripts/{script_id}/assign           assign evaluator
  PATCH  /scripts/{script_id}/marks            evaluator saves marks (no gate)
  POST   /scripts/{script_id}/submit           Gate 1: evaluator submits all marks
  POST   /scripts/{script_id}/finalise         Gate 2: Board finalises + writes ledger
  GET    /scripts/{script_id}/review           enriched evaluator review panel (H-36)
  POST   /scripts/{script_id}/accept           accept AI suggestions (H-36)
  POST   /scripts/{script_id}/override-quality admin overrides QUALITY_FAILED (H-36)
  GET    /scripts/{script_id}/file-url         presigned URL for uploaded scan (H-36)
  GET    /scripts/{script_id}/evaluations      AI suggestions + evaluator marks
  GET    /scripts/{script_id}/ledger           Board-finalised score record
  GET    /scripts/{script_id}/comparison       Board Gate 2 — PRIMARY+SECONDARY side-by-side (M09.1)
  POST   /scripts/{script_id}/board-adjust     Board sets adjusted marks per question (M09.1)
  GET    /scripts/ledger/paper/{paper_id}      all finalised scores for a paper
  GET    /scripts/ledger/paper/{paper_id}/export  CSV download of score ledger (H-36)

Static paths (/board/pending, /evaluator/me, /paper/..., /stats, /ledger/...) are
declared before /{script_id} so FastAPI routes them as literals, not path parameters.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_context_dep, require_roles, require_responsibility
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m09_paper_admin.schemas import (
    AcceptSuggestionsRequest,
    BoardAdjustRequest,
    BoardApproveRequest,
    BoardComparisonResponse,
    BoardCourseApprovalResponse,
    BoardRejectRequest,
    BoardSessionCreateRequest,
    BoardSessionListResponse,
    BoardSessionResponse,
    BoardStatisticsResponse,
    BulkMarkUpdate,
    DigitalAttemptDetailResponse,
    DigitalAttemptResponse,
    DigitalResponseIn,
    DigitalResponseOut,
    DigitalResultResponse,
    DigitalSessionAnalyticsResponse,
    DigitalSessionCreate,
    DigitalSessionListResponse,
    DigitalSessionResponse,
    EvaluatorReviewResponse,
    ExamScoreLedgerListResponse,
    ExamScoreLedgerResponse,
    FacultyScoreIn,
    JobStatusResponse,
    ModerationFlagRequest,
    ModerationHistoryResponse,
    ModerationQueueResponse,
    ModerationReviewResponse,
    ModerationSubmitRequest,
    PaperPipelineStats,
    QualityOverrideRequest,
    RevaluationAcceptRequest,
    RevaluationBoardRatifyRequest,
    RevaluationBoardRejectRequest,
    RevaluationCreateRequest,
    RevaluationDetailResponse,
    RevaluationRejectRequest,
    RevaluationRequestListResponse,
    RevaluationRequestResponse,
    RevaluationSubmitMarksRequest,
    ScannedScriptListResponse,
    ScannedScriptResponse,
    ScriptAssignEvaluatorRequest,
    ScriptEvaluationResponse,
    ScriptFileUrlResponse,
    ScriptFinaliseRequest,
    ScriptIngestRequest,
    ScriptSubmitMarksRequest,
    ScriptVarianceResponse,
    SubjectiveQueueResponse,
    SubjectiveReviewResponse,
    SubjectiveScoreOut,
    SubjectiveSubmitIn,
    SubjectiveSubmitResult,
)
from app.modules.m09_paper_admin.service import (
    BoardApprovalService,
    DigitalExamError,
    DigitalExamService,
    ModerationService,
    RevaluationService,
    ScriptService,
    ScriptServiceError,
)

router = APIRouter(tags=["M09 Paper Admin"])

# ---------------------------------------------------------------------------
# Role groups
# ---------------------------------------------------------------------------

_INGEST   = [TenantRole.ADMIN, TenantRole.BOARD]
_EVALUATE = [TenantRole.FACULTY, TenantRole.ADMIN]
_BOARD    = [TenantRole.BOARD, TenantRole.ADMIN]
_READ     = [TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY, TenantRole.BOARD]


_ADMIN_ONLY      = [TenantRole.ADMIN]
_MODERATE        = [TenantRole.DEAN, TenantRole.ADMIN]  # M09.2: who can moderate
_BOARD_APPROVE   = [TenantRole.DEAN, TenantRole.ADMIN]  # M09.4: who can approve/reject results
_DIGITAL_ADMIN   = [TenantRole.ADMIN, TenantRole.BOARD]  # M09.5: session management
_DIGITAL_READ    = [TenantRole.ADMIN, TenantRole.BOARD, TenantRole.DEAN]  # M09.5: view sessions/results
_STUDENT_ONLY    = [TenantRole.STUDENT]  # M09.5: exam taking
_FACULTY_REVIEW  = [TenantRole.FACULTY, TenantRole.ADMIN]  # M09.5 Phase D: subjective scoring

def _ingest_dep():          return require_roles(*_INGEST)
def _eval_dep():            return require_responsibility(*_EVALUATE)
def _board_dep():           return require_roles(*_BOARD)
def _read_dep():            return require_roles(*_READ)
def _admin_dep():           return require_roles(*_ADMIN_ONLY)
def _moderate_dep():        return require_roles(*_MODERATE)
def _board_approve_dep():   return require_roles(*_BOARD_APPROVE)
def _digital_admin_dep():   return require_roles(*_DIGITAL_ADMIN)
def _digital_read_dep():    return require_roles(*_DIGITAL_READ)
def _student_dep():         return require_roles(*_STUDENT_ONLY)
def _faculty_review_dep():  return require_responsibility(*_FACULTY_REVIEW)


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------

def _raise(exc: ScriptServiceError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "message": exc.message},
    )


def _raise_digital(exc: DigitalExamError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ---------------------------------------------------------------------------
# POST /upload — ingest scanned script
# ---------------------------------------------------------------------------

@router.post("/upload", status_code=202)
async def upload_script(
    payload:    ScriptIngestRequest,
    upload_url: str | None = Query(default=None, description="S3 object key of uploaded scan"),
    page_count: int | None = Query(default=None, ge=1),
    current_user: CurrentUser = Depends(_ingest_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Register a scanned answer script and queue the AI scoring task.
    The PDF/scan must already be uploaded to S3; pass the object key as upload_url.
    Returns 202 Accepted with script_id, masked_id, and job_id for polling.
    """
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        script, job_id = await ScriptService.ingest_script(
            payload,
            upload_url=upload_url,
            page_count=page_count,
            ingested_by=current_user.user_id,
            tenant_id=tenant_id,
            schema_name=schema,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)

    return {
        "script_id": str(script.id),
        "masked_id": script.masked_id,
        "job_id":    str(job_id),
        "status":    script.status,
    }


# ---------------------------------------------------------------------------
# GET /board/pending — STATIC (must be before /{script_id})
# ---------------------------------------------------------------------------

@router.get("/board/pending", response_model=ScannedScriptListResponse)
async def list_board_pending(
    offset: int = Query(default=0, ge=0),
    limit:  int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Board: list scripts awaiting finalisation (status = MARKS_SUBMITTED)."""
    db: AsyncSession = db_info["db"]

    items, total = await ScriptService.list_board_pending(offset=offset, limit=limit, db=db)
    return ScannedScriptListResponse(
        items=[ScannedScriptResponse.model_validate(s) for s in items],
        total=total, offset=offset, limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /evaluator/me — STATIC (must be before /{script_id})
# ---------------------------------------------------------------------------

@router.get("/evaluator/me", response_model=ScannedScriptListResponse)
async def list_my_scripts(
    status: str | None = Query(default=None),
    offset: int        = Query(default=0, ge=0),
    limit:  int        = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(_eval_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Evaluator: list scripts assigned to the authenticated user."""
    db: AsyncSession = db_info["db"]

    items, total = await ScriptService.list_for_evaluator(
        current_user.user_id, status=status, offset=offset, limit=limit, db=db,
    )
    return ScannedScriptListResponse(
        items=[ScannedScriptResponse.model_validate(s) for s in items],
        total=total, offset=offset, limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /paper/{paper_id} — STATIC (must be before /{script_id})
# ---------------------------------------------------------------------------

@router.get("/paper/{paper_id}", response_model=ScannedScriptListResponse)
async def list_scripts_for_paper(
    paper_id: UUID,
    status:   str | None = Query(default=None),
    offset:   int        = Query(default=0, ge=0),
    limit:    int        = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """List all scripts for an exam paper (identity masked pre-finalise)."""
    db: AsyncSession = db_info["db"]

    items, total = await ScriptService.list_for_paper(
        paper_id, status=status, offset=offset, limit=limit, db=db,
    )
    return ScannedScriptListResponse(
        items=[ScannedScriptResponse.model_validate(s) for s in items],
        total=total, offset=offset, limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /stats — paper pipeline stats (STEP-10, STATIC — must be before GET /)
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=PaperPipelineStats)
async def get_paper_stats(
    paper_id: UUID = Query(..., description="Exam paper UUID"),
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Board/Admin: aggregate pipeline-status counts for all scripts in an exam paper.
    Returns per-status counts and completion_pct (board_finalised / total × 100).
    Read-only — no workflow mutations.
    """
    db: AsyncSession = db_info["db"]
    return await ScriptService.get_paper_stats(paper_id, db=db)


# ---------------------------------------------------------------------------
# GET / — list all scripts
# ---------------------------------------------------------------------------

@router.get("", response_model=ScannedScriptListResponse)
async def list_all_scripts(
    exam_paper_id: UUID | None = Query(default=None),
    status:        str | None  = Query(default=None),
    offset:        int         = Query(default=0, ge=0),
    limit:         int         = Query(default=50, ge=1, le=200),
    current_user: CurrentUser  = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Admin/Board: list all scripts for the tenant, optionally filtered."""
    db: AsyncSession = db_info["db"]

    items, total = await ScriptService.list_scripts(
        exam_paper_id=exam_paper_id, status=status, offset=offset, limit=limit, db=db,
    )
    return ScannedScriptListResponse(
        items=[ScannedScriptResponse.model_validate(s) for s in items],
        total=total, offset=offset, limit=limit,
    )


# ---------------------------------------------------------------------------
# M09.2 Moderation routes — all STATIC paths; declared before /{script_id}
# ---------------------------------------------------------------------------

@router.get("/moderation/queue", response_model=ModerationQueueResponse)
async def get_moderation_queue(
    paper_id: UUID = Query(..., description="Exam paper UUID"),
    offset:   int  = Query(default=0, ge=0),
    limit:    int  = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(_moderate_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Dean/Admin: list all PENDING moderation reviews for an exam paper.
    Sorted by variance_pct descending (highest variance first).
    """
    db: AsyncSession = db_info["db"]
    items, total = await ModerationService.list_moderation_queue(
        paper_id, offset=offset, limit=limit, db=db
    )
    return ModerationQueueResponse(
        items=[ModerationReviewResponse.model_validate(r) for r in items],
        total=total, offset=offset, limit=limit,
    )


@router.post("/paper/{paper_id}/auto-flag-moderation")
async def auto_flag_moderation(
    paper_id:     UUID,
    current_user: CurrentUser = Depends(_moderate_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Dean/Admin: scan all MARKS_SUBMITTED double-evaluation scripts for this paper
    and auto-flag those exceeding the paper's discrepancy threshold.
    Returns counts: checked, flagged, already_pending, skipped.
    """
    db: AsyncSession = db_info["db"]
    tenant_id: UUID  = db_info["tenant_id"]
    try:
        result = await ModerationService.auto_flag_paper(
            paper_id,
            flagged_by=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return result


# ---------------------------------------------------------------------------
# GET /{script_id} — script detail
# ---------------------------------------------------------------------------

@router.get("/{script_id}", response_model=ScannedScriptResponse)
async def get_script(
    script_id:        UUID,
    include_identity: bool = Query(
        default=False,
        description="Include student identity (only honoured after BOARD_FINALISED).",
    ),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Get script detail.  Student identity masked unless status == BOARD_FINALISED
    and include_identity=True is requested by an authorised caller.
    """
    db: AsyncSession = db_info["db"]

    # Only BOARD/ADMIN may request identity reveal
    can_see_identity = current_user.role in ("BOARD", "ADMIN")
    effective_include = include_identity and can_see_identity

    try:
        script = await ScriptService.get_script(
            script_id, include_identity=effective_include, db=db
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return ScannedScriptResponse.model_validate(script)


# ---------------------------------------------------------------------------
# POST /{script_id}/assign — assign evaluator
# ---------------------------------------------------------------------------

@router.post("/{script_id}/assign", response_model=ScannedScriptResponse)
async def assign_evaluator(
    script_id: UUID,
    payload:   ScriptAssignEvaluatorRequest,
    current_user: CurrentUser = Depends(_ingest_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Admin/Board: assign a primary (and optional secondary) evaluator to a script."""
    db: AsyncSession = db_info["db"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        script = await ScriptService.assign_evaluator(
            script_id,
            payload,
            assigned_by=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return ScannedScriptResponse.model_validate(script)


# ---------------------------------------------------------------------------
# PATCH /{script_id}/marks — evaluator saves marks (no gate)
# ---------------------------------------------------------------------------

@router.patch("/{script_id}/marks", response_model=list[ScriptEvaluationResponse])
async def update_marks(
    script_id: UUID,
    payload:   BulkMarkUpdate,
    current_user: CurrentUser = Depends(_eval_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Evaluator saves marks for one or more questions without triggering Gate 1.
    Allowed only when script status is SCORED or REVIEW_REQUIRED.
    """
    db: AsyncSession = db_info["db"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        evals = await ScriptService.update_evaluator_marks(
            script_id,
            payload,
            evaluator_user_id=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return [ScriptEvaluationResponse.model_validate(e) for e in evals]


# ---------------------------------------------------------------------------
# POST /{script_id}/submit — Gate 1: evaluator submits all marks
# ---------------------------------------------------------------------------

@router.post("/{script_id}/submit", response_model=ScannedScriptResponse)
async def submit_marks(
    script_id: UUID,
    payload:   ScriptSubmitMarksRequest,
    current_user: CurrentUser = Depends(_eval_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    GATE 1: Evaluator submits all marks.  Status → MARKS_SUBMITTED.
    All evaluations must have evaluator_marks set; missing marks cause 400.
    Only the assigned evaluator (primary or secondary) may submit.
    """
    db: AsyncSession = db_info["db"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        script = await ScriptService.submit_marks(
            script_id,
            payload,
            evaluator_user_id=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return ScannedScriptResponse.model_validate(script)


# ---------------------------------------------------------------------------
# POST /{script_id}/finalise — Gate 2: Board finalises and writes ledger
# ---------------------------------------------------------------------------

@router.post("/{script_id}/finalise", response_model=dict)
async def board_finalise(
    script_id: UUID,
    payload:   ScriptFinaliseRequest,
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    GATE 2: Board member finalises marks.
    Copies evaluator_marks → final_marks, writes exam_score_ledger (append-only),
    advances script status → BOARD_FINALISED, reveals student identity.
    """
    db: AsyncSession = db_info["db"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        script, ledger = await ScriptService.board_finalise(
            script_id,
            payload,
            board_user_id=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)

    return {
        "script":  ScannedScriptResponse.model_validate(script).model_dump(),
        "ledger":  ExamScoreLedgerResponse.model_validate(ledger).model_dump(),
    }


# ---------------------------------------------------------------------------
# GET /{script_id}/review — evaluator review panel (STEP-05)
# ---------------------------------------------------------------------------

@router.get("/{script_id}/review", response_model=EvaluatorReviewResponse)
async def get_evaluator_review(
    script_id: UUID,
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Evaluator review panel: script with OCR text + enriched AI evaluations.
    FACULTY callers are restricted to scripts they are assigned to.
    ADMIN / BOARD / DEAN can view any script (oversight).
    Identity is always masked (BOARD_FINALISED scripts excluded from this panel).
    """
    db: AsyncSession = db_info["db"]

    try:
        script, evals = await ScriptService.get_evaluator_review(
            script_id,
            requesting_user_id=current_user.user_id,
            user_role=current_user.role,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)

    return EvaluatorReviewResponse(
        script_id=script.id,
        masked_id=script.masked_id,
        exam_paper_id=script.exam_paper_id,
        status=script.status,
        ocr_text=script.ocr_text,
        ocr_status=script.ocr_status,
        page_count=script.page_count,
        page_image_keys=script.page_image_keys,
        objective_auto_score=(
            float(script.objective_auto_score)
            if script.objective_auto_score is not None else None
        ),
        evaluations=[ScriptEvaluationResponse.model_validate(e) for e in evals],
    )


# ---------------------------------------------------------------------------
# POST /{script_id}/accept — evaluator accepts AI suggestions (STEP-05)
# ---------------------------------------------------------------------------

@router.post("/{script_id}/accept", response_model=list[ScriptEvaluationResponse])
async def accept_suggestions(
    script_id: UUID,
    payload:   AcceptSuggestionsRequest,
    current_user: CurrentUser = Depends(_eval_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Evaluator accepts AI-suggested marks for specified questions (or all).
    Copies ai_suggested_marks → evaluator_marks.  Never writes final_marks.
    Script status stays SCORED or REVIEW_REQUIRED — Gate 1 is not triggered.
    """
    db: AsyncSession = db_info["db"]
    tenant_id: UUID  = db_info["tenant_id"]

    question_ids = (
        [UUID(qid) for qid in payload.question_ids]
        if payload.question_ids is not None else None
    )

    try:
        evals = await ScriptService.accept_suggestions(
            script_id,
            question_ids,
            evaluator_note=payload.evaluator_note,
            evaluator_user_id=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return [ScriptEvaluationResponse.model_validate(e) for e in evals]


# ---------------------------------------------------------------------------
# POST /{script_id}/override-quality — H-36 STEP-12 admin override
# ---------------------------------------------------------------------------

@router.post("/{script_id}/override-quality", response_model=ScannedScriptResponse)
async def override_quality_failed(
    script_id: UUID,
    payload:   QualityOverrideRequest,
    current_user: CurrentUser = Depends(_admin_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    ADMIN-ONLY: override a QUALITY_FAILED script to proceed to OCR.

    Requires status == QUALITY_FAILED.  A mandatory reason string is stored in
    the audit log.  Dispatches ocr_scanned_script — if the script has no upload_url
    (unusual), the task will fail gracefully and set status → FAILED.

    This is a named human action — the admin's user_id is audit-logged.
    No automatic trigger is allowed.
    """
    db: AsyncSession  = db_info["db"]
    schema: str       = db_info["schema_name"]
    tenant_id: UUID   = db_info["tenant_id"]

    try:
        script = await ScriptService.override_quality_failed(
            script_id,
            payload,
            admin_user_id=current_user.user_id,
            tenant_id=tenant_id,
            schema_name=schema,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return ScannedScriptResponse.model_validate(script)


# ---------------------------------------------------------------------------
# GET /{script_id}/file-url — presigned URL for script scan (H-36 STEP-13)
# ---------------------------------------------------------------------------

@router.get("/{script_id}/file-url", response_model=ScriptFileUrlResponse)
async def get_script_file_url(
    script_id: UUID,
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Return a 5-minute presigned GET URL for the uploaded script PDF/image.

    ADMIN and BOARD can access any script.  FACULTY callers must be the
    assigned evaluator or second evaluator.  Returns HTTP 404 when the
    script has no uploaded file (digital-only exam path).
    """
    db: AsyncSession = db_info["db"]

    try:
        url = await ScriptService.get_script_file_url(
            script_id,
            caller_user_id=current_user.user_id,
            caller_role=current_user.role.value,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return ScriptFileUrlResponse(url=url, expires_in=300)


# ---------------------------------------------------------------------------
# GET /{script_id}/evaluations — AI suggestions + evaluator marks
# ---------------------------------------------------------------------------

@router.get("/{script_id}/evaluations", response_model=list[ScriptEvaluationResponse])
async def get_evaluations(
    script_id: UUID,
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Return AI-suggested marks and evaluator marks for all questions in a script."""
    db: AsyncSession = db_info["db"]

    try:
        evals = await ScriptService.get_evaluations(script_id, db=db)
    except ScriptServiceError as exc:
        _raise(exc)
    return [ScriptEvaluationResponse.model_validate(e) for e in evals]


# ---------------------------------------------------------------------------
# GET /{script_id}/ledger — Board-finalised score record
# ---------------------------------------------------------------------------

@router.get("/{script_id}/ledger", response_model=ExamScoreLedgerResponse)
async def get_ledger_entry(
    script_id: UUID,
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Return the Board-finalised score ledger entry.
    Only accessible after status == BOARD_FINALISED.
    Returns 403 for pre-finalised scripts.
    """
    db: AsyncSession = db_info["db"]

    try:
        entry = await ScriptService.get_ledger_entry(script_id, db=db)
    except ScriptServiceError as exc:
        _raise(exc)
    return ExamScoreLedgerResponse.model_validate(entry)


# ---------------------------------------------------------------------------
# GET /ledger/paper/{paper_id} — all ledger entries for a paper
# ---------------------------------------------------------------------------

@router.get("/ledger/paper/{paper_id}", response_model=ExamScoreLedgerListResponse)
async def list_ledger_for_paper(
    paper_id: UUID,
    offset:   int = Query(default=0, ge=0),
    limit:    int = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Board/Admin: list all finalised score records for an exam paper."""
    db: AsyncSession = db_info["db"]

    items, total = await ScriptService.list_ledger_for_paper(
        paper_id, offset=offset, limit=limit, db=db,
    )
    return ExamScoreLedgerListResponse(
        items=[ExamScoreLedgerResponse.model_validate(e) for e in items],
        total=total, offset=offset, limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /ledger/paper/{paper_id}/export — CSV download (H-36 STEP-11)
# ---------------------------------------------------------------------------

@router.get("/ledger/paper/{paper_id}/export")
async def export_ledger_csv(
    paper_id: UUID,
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Board/Admin: download all Board-finalised scores for an exam paper as CSV.
    Returns text/csv with Content-Disposition attachment so the browser saves the file.
    student_user_id is excluded; student_roll_ref is included post-finalisation.
    """
    db: AsyncSession = db_info["db"]
    csv_text = await ScriptService.export_ledger_csv(paper_id, db=db)
    filename  = f"score_ledger_{str(paper_id)[:8]}.csv"
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# GET /{script_id}/comparison — Board comparison view (M09.1)
# ---------------------------------------------------------------------------

@router.get("/{script_id}/comparison", response_model=BoardComparisonResponse)
async def get_board_comparison(
    script_id: UUID,
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Board Gate 2 double-evaluation comparison view.

    Returns PRIMARY and SECONDARY evaluation rows side-by-side with per-evaluator
    totals and a flag indicating whether Board adjustments have been set.
    Requires status == MARKS_SUBMITTED.
    Identity is masked (student_user_id / student_roll_ref not exposed here).

    For single-evaluator papers secondary_evaluations is empty and
    secondary_total is 0.0 — the Board can still use this view to inspect
    the primary evaluation before calling /finalise.
    """
    db: AsyncSession = db_info["db"]

    try:
        result = await ScriptService.get_board_comparison(script_id, db=db)
    except ScriptServiceError as exc:
        _raise(exc)
    return result


# ---------------------------------------------------------------------------
# POST /{script_id}/board-adjust — Board sets per-question adjusted marks (M09.1)
# ---------------------------------------------------------------------------

@router.post("/{script_id}/board-adjust", response_model=list[ScriptEvaluationResponse])
async def board_adjust_marks(
    script_id: UUID,
    payload:   BoardAdjustRequest,
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Board sets adjusted marks for specified questions.

    For double-evaluation papers: required before /finalise so the Board can
    explicitly decide the official mark for every question after reviewing both
    evaluations.  NO automatic averaging — the Board must enter each mark.

    For single-evaluator papers: optional correction mechanism before finalisation.

    Requires status == MARKS_SUBMITTED.  Does NOT advance status.
    Returns updated PRIMARY evaluation rows with board_adjusted_marks populated.

    Human-gate invariant: only /finalise copies marks → final_marks and writes
    the exam_score_ledger.  This endpoint only sets board_adjusted_marks.
    """
    db: AsyncSession = db_info["db"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        evals = await ScriptService.set_board_adjusted_marks(
            script_id,
            payload,
            board_user_id=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return [ScriptEvaluationResponse.model_validate(e) for e in evals]


# ---------------------------------------------------------------------------
# M09.2 — script-level moderation endpoints
# ---------------------------------------------------------------------------

@router.get("/{script_id}/variance", response_model=ScriptVarianceResponse)
async def get_script_variance(
    script_id: UUID,
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Board/Dean/Admin: show primary vs secondary evaluator totals and variance %.
    Available for double-evaluation scripts from SECONDARY_EVALUATED status onward.
    Identity is always masked.
    """
    db: AsyncSession = db_info["db"]
    try:
        result = await ModerationService.get_variance(script_id, db=db)
    except ScriptServiceError as exc:
        _raise(exc)
    return result


@router.post("/{script_id}/flag-moderation", response_model=ModerationReviewResponse)
async def flag_for_moderation(
    script_id: UUID,
    payload:   ModerationFlagRequest,
    current_user: CurrentUser = Depends(_moderate_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Dean/Admin: manually flag a MARKS_SUBMITTED script for moderation review.
    Creates a moderation review record and advances status → MODERATION_PENDING.
    """
    db: AsyncSession = db_info["db"]
    tenant_id: UUID  = db_info["tenant_id"]
    try:
        review = await ModerationService.flag_for_moderation(
            script_id,
            reason=payload.reason,
            flagged_by=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return ModerationReviewResponse.model_validate(review)


@router.post("/{script_id}/moderate", response_model=ModerationHistoryResponse)
async def submit_moderation(
    script_id: UUID,
    payload:   ModerationSubmitRequest,
    current_user: CurrentUser = Depends(_moderate_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Dean/Admin: submit per-question moderation marks for a MODERATION_PENDING script.

    All PRIMARY round questions must be covered.
    moderation_notes (≥20 chars) is mandatory.
    Creates MODERATION round ScriptEvaluation rows; status → MODERATION_COMPLETE.
    Board finalise will use MODERATION marks as the authoritative scores.
    """
    db: AsyncSession = db_info["db"]
    tenant_id: UUID  = db_info["tenant_id"]
    try:
        review, _ = await ModerationService.submit_moderation(
            script_id,
            payload,
            moderator_id=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return await ModerationService.get_moderation_history(script_id, db=db)


@router.get("/{script_id}/moderation-history", response_model=ModerationHistoryResponse)
async def get_moderation_history(
    script_id: UUID,
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Board/Dean/Admin: full moderation audit trail for a script.
    Returns the moderation review record plus PRIMARY, SECONDARY, and MODERATION
    evaluation rounds side by side.
    """
    db: AsyncSession = db_info["db"]
    try:
        result = await ModerationService.get_moderation_history(script_id, db=db)
    except ScriptServiceError as exc:
        _raise(exc)
    return result


# ---------------------------------------------------------------------------
# M09.4 — Board Approval Endpoints
# Note: placed after /{script_id} routes; /board/ prefix avoids collisions.
# ---------------------------------------------------------------------------

@router.post("/board/sessions", response_model=BoardSessionResponse)
async def convene_board_session(
    payload: BoardSessionCreateRequest,
    current_user: CurrentUser = Depends(_board_approve_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Dean/Admin: convene a board session for an exam paper's results.
    Requires at least one BOARD_FINALISED script. Computes aggregate statistics
    (mean, pass rate) at convene time.
    """
    db: AsyncSession = db_info["db"]
    tenant_id = db_info["tenant_id"]
    try:
        session = await BoardApprovalService.convene(
            payload.exam_paper_id,
            payload.session_title,
            payload.pass_mark_pct,
            convened_by=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return session


@router.get("/board/sessions", response_model=BoardSessionListResponse)
async def list_board_sessions(
    paper_id: UUID = Query(..., description="Exam paper ID"),
    offset: int = Query(default=0, ge=0),
    limit: int  = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(_board_approve_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Dean/Admin: list board sessions for an exam paper."""
    db: AsyncSession = db_info["db"]
    items, total = await BoardApprovalService.list_sessions(
        paper_id, offset=offset, limit=limit, db=db
    )
    return BoardSessionListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/board/sessions/{session_id}", response_model=BoardSessionResponse)
async def get_board_session(
    session_id: UUID,
    current_user: CurrentUser = Depends(_board_approve_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Dean/Admin: get board session details."""
    db: AsyncSession = db_info["db"]
    try:
        session = await BoardApprovalService.get_session(session_id, db=db)
    except ScriptServiceError as exc:
        _raise(exc)
    return session


@router.get("/board/sessions/{session_id}/statistics", response_model=BoardCourseApprovalResponse)
async def get_board_session_statistics(
    session_id: UUID,
    current_user: CurrentUser = Depends(_board_approve_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Dean/Admin: computed statistics for a board session."""
    db: AsyncSession = db_info["db"]
    try:
        stats = await BoardApprovalService.get_statistics(session_id, db=db)
    except ScriptServiceError as exc:
        _raise(exc)
    if stats is None:
        raise HTTPException(status_code=404, detail="No statistics found for this session.")
    return stats


@router.post("/board/sessions/{session_id}/approve", response_model=BoardSessionResponse)
async def approve_board_session(
    session_id: UUID,
    payload: BoardApproveRequest,
    current_user: CurrentUser = Depends(_board_approve_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Dean/Admin: Board approves results.
    After approval, no mark adjustments are permitted (results locked).
    Only valid when session status is OPEN.
    """
    db: AsyncSession = db_info["db"]
    tenant_id = db_info["tenant_id"]
    try:
        session = await BoardApprovalService.approve(
            session_id,
            payload.board_remarks,
            decided_by=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return session


@router.post("/board/sessions/{session_id}/reject", response_model=BoardSessionResponse)
async def reject_board_session(
    session_id: UUID,
    payload: BoardRejectRequest,
    current_user: CurrentUser = Depends(_board_approve_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Dean/Admin: Board rejects results.
    Session moves to REJECTED; scripts may be re-evaluated and a new session convened.
    Only valid when session status is OPEN.
    """
    db: AsyncSession = db_info["db"]
    tenant_id = db_info["tenant_id"]
    try:
        session = await BoardApprovalService.reject(
            session_id,
            payload.board_remarks,
            decided_by=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return session


@router.post("/board/sessions/{session_id}/declare", response_model=BoardSessionResponse)
async def declare_results(
    session_id: UUID,
    current_user: CurrentUser = Depends(_admin_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Admin only: publish results to students.
    Only valid when session status is APPROVED.
    """
    db: AsyncSession = db_info["db"]
    tenant_id = db_info["tenant_id"]
    try:
        session = await BoardApprovalService.declare(
            session_id,
            declared_by=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return session


@router.get("/board/paper/{paper_id}/status")
async def get_board_status(
    paper_id: UUID,
    current_user: CurrentUser = Depends(_board_approve_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Dean/Admin/Board: current board gate status for a paper."""
    db: AsyncSession = db_info["db"]
    return await BoardApprovalService.get_board_status(paper_id, db=db)


# ---------------------------------------------------------------------------
# M09.3 — Revaluation Workflow Endpoints
# ---------------------------------------------------------------------------

_STUDENT_ONLY = [TenantRole.STUDENT]
_REVAL_ADMIN  = [TenantRole.ADMIN, TenantRole.DEAN]
_REVAL_BOARD  = [TenantRole.DEAN, TenantRole.ADMIN, TenantRole.BOARD]


@router.post("/revaluation/requests", response_model=RevaluationRequestResponse)
async def submit_revaluation_request(
    payload: RevaluationCreateRequest,
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db_info=Depends(get_tenant_context_dep),
):
    """Student: submit a revaluation request for a script."""
    db: AsyncSession = db_info["db"]
    tenant_id = db_info["tenant_id"]
    try:
        req = await RevaluationService.submit_request(
            payload.script_id,
            payload.reason,
            payload.payment_reference,
            student_user_id=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return req


@router.get("/revaluation/requests/my", response_model=RevaluationRequestListResponse)
async def list_my_revaluation_requests(
    offset: int = Query(default=0, ge=0),
    limit:  int = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db_info=Depends(get_tenant_context_dep),
):
    """Student: list my revaluation requests."""
    db: AsyncSession = db_info["db"]
    items = await RevaluationService.list_my_requests(
        current_user.user_id, offset=offset, limit=limit, db=db
    )
    return RevaluationRequestListResponse(
        items=items, total=len(items), offset=offset, limit=limit
    )


@router.get("/revaluation/requests", response_model=RevaluationRequestListResponse)
async def list_revaluation_requests(
    paper_id: UUID = Query(..., description="Exam paper ID"),
    status:   str | None = Query(default=None),
    offset:   int = Query(default=0, ge=0),
    limit:    int = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_roles(*_REVAL_ADMIN)),
    db_info=Depends(get_tenant_context_dep),
):
    """Admin/Dean: list revaluation requests for a paper."""
    db: AsyncSession = db_info["db"]
    items = await RevaluationService.list_requests_for_paper(
        paper_id, status=status, offset=offset, limit=limit, db=db
    )
    return RevaluationRequestListResponse(
        items=items, total=len(items), offset=offset, limit=limit
    )


@router.get("/revaluation/requests/{request_id}", response_model=RevaluationDetailResponse)
async def get_revaluation_request(
    request_id: UUID,
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Get revaluation request detail. Students may only view their own."""
    db: AsyncSession = db_info["db"]
    try:
        result = await RevaluationService.get_request_detail(
            request_id,
            requester_user_id=current_user.user_id,
            requester_role=current_user.role,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return result


@router.post("/revaluation/requests/{request_id}/accept", response_model=RevaluationRequestResponse)
async def accept_revaluation_request(
    request_id: UUID,
    payload: RevaluationAcceptRequest,
    current_user: CurrentUser = Depends(require_roles(*_REVAL_ADMIN)),
    db_info=Depends(get_tenant_context_dep),
):
    """Admin: accept revaluation request and assign evaluator."""
    db: AsyncSession = db_info["db"]
    tenant_id = db_info["tenant_id"]
    try:
        req = await RevaluationService.accept_request(
            request_id,
            payload.assigned_evaluator_id,
            payload.admin_notes,
            admin_user_id=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return req


@router.post("/revaluation/requests/{request_id}/reject", response_model=RevaluationRequestResponse)
async def reject_revaluation_request(
    request_id: UUID,
    payload: RevaluationRejectRequest,
    current_user: CurrentUser = Depends(require_roles(*_REVAL_ADMIN)),
    db_info=Depends(get_tenant_context_dep),
):
    """Admin: reject revaluation request at intake."""
    db: AsyncSession = db_info["db"]
    tenant_id = db_info["tenant_id"]
    try:
        req = await RevaluationService.reject_request(
            request_id,
            payload.admin_notes,
            admin_user_id=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return req


@router.post("/revaluation/requests/{request_id}/submit-marks", response_model=RevaluationRequestResponse)
async def submit_revaluation_marks(
    request_id: UUID,
    payload: RevaluationSubmitMarksRequest,
    current_user: CurrentUser = Depends(require_responsibility(TenantRole.FACULTY, TenantRole.ADMIN)),
    db_info=Depends(get_tenant_context_dep),
):
    """Faculty (assigned evaluator, or a DEAN holding an active FACULTY grant): submit per-question revaluation marks."""
    db: AsyncSession = db_info["db"]
    tenant_id = db_info["tenant_id"]
    try:
        req = await RevaluationService.submit_revaluation_marks(
            request_id,
            payload.marks,
            payload.submission_note,
            evaluator_user_id=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return req


@router.post("/revaluation/requests/{request_id}/board-ratify", response_model=RevaluationRequestResponse)
async def board_ratify_revaluation(
    request_id: UUID,
    payload: RevaluationBoardRatifyRequest,
    current_user: CurrentUser = Depends(require_roles(*_REVAL_BOARD)),
    db_info=Depends(get_tenant_context_dep),
):
    """Dean/Board/Admin: ratify revaluation outcome — awarded_total = max(original, revaluation)."""
    db: AsyncSession = db_info["db"]
    tenant_id = db_info["tenant_id"]
    try:
        req = await RevaluationService.board_ratify(
            request_id,
            payload.board_remarks,
            decided_by=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return req


@router.post("/revaluation/requests/{request_id}/board-reject", response_model=RevaluationRequestResponse)
async def board_reject_revaluation(
    request_id: UUID,
    payload: RevaluationBoardRejectRequest,
    current_user: CurrentUser = Depends(require_roles(*_REVAL_BOARD)),
    db_info=Depends(get_tenant_context_dep),
):
    """Dean/Board/Admin: reject revaluation outcome — original marks stand."""
    db: AsyncSession = db_info["db"]
    tenant_id = db_info["tenant_id"]
    try:
        req = await RevaluationService.board_reject(
            request_id,
            payload.board_remarks,
            decided_by=current_user.user_id,
            tenant_id=tenant_id,
            db=db,
        )
    except ScriptServiceError as exc:
        _raise(exc)
    return req


# ---------------------------------------------------------------------------
# Digital Exams — M09.5
# Route summary
#   POST   /digital/sessions                      Admin: create session
#   PATCH  /digital/sessions/{id}/activate        Admin: open to students
#   PATCH  /digital/sessions/{id}/close           Admin: close session
#   GET    /digital/sessions                      Admin/Board: list sessions
#   GET    /digital/sessions/{id}                 Admin/Board: session detail
#   POST   /digital/sessions/{id}/attempt         Student: start/resume attempt
#   GET    /digital/attempts/{id}/questions       Student: get questions
#   PUT    /digital/attempts/{id}/responses/{qid} Student: save response
#   POST   /digital/attempts/{id}/submit          Student: final submit
#   GET    /digital/attempts/{id}/result          Student/Admin: view result
# ---------------------------------------------------------------------------


@router.post("/digital/sessions", response_model=DigitalSessionResponse, status_code=201)
async def create_digital_session(
    payload: DigitalSessionCreate,
    current_user: CurrentUser = Depends(_digital_admin_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Admin/Board: create a digital exam delivery session for an exam paper."""
    db: AsyncSession = db_info["db"]
    try:
        session = await DigitalExamService.create_session(
            exam_paper_id=payload.exam_paper_id,
            created_by=current_user.user_id,
            title=payload.title,
            max_duration_mins=payload.max_duration_mins,
            window_start=payload.window_start,
            window_end=payload.window_end,
            instructions=payload.instructions,
            db=db,
        )
    except DigitalExamError as exc:
        _raise_digital(exc)
    out = DigitalSessionResponse.model_validate(session)
    out.attempt_count = 0
    out.scored_count = 0
    return out


@router.patch("/digital/sessions/{session_id}/activate", response_model=DigitalSessionResponse)
async def activate_digital_session(
    session_id: UUID,
    current_user: CurrentUser = Depends(_digital_admin_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Admin/Board: open session — students can now start attempts."""
    db: AsyncSession = db_info["db"]
    try:
        session = await DigitalExamService.activate_session(
            session_id, actor_user_id=current_user.user_id, db=db
        )
    except DigitalExamError as exc:
        _raise_digital(exc)
    out = DigitalSessionResponse.model_validate(session)
    out.attempt_count = 0
    out.scored_count = 0
    return out


@router.patch("/digital/sessions/{session_id}/close", response_model=DigitalSessionResponse)
async def close_digital_session(
    session_id: UUID,
    current_user: CurrentUser = Depends(_digital_admin_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Admin/Board: close session — no new attempts accepted."""
    db: AsyncSession = db_info["db"]
    try:
        session = await DigitalExamService.close_session(
            session_id, actor_user_id=current_user.user_id, db=db
        )
    except DigitalExamError as exc:
        _raise_digital(exc)
    out = DigitalSessionResponse.model_validate(session)
    out.attempt_count = 0
    out.scored_count = 0
    return out


@router.get("/digital/sessions", response_model=DigitalSessionListResponse)
async def list_digital_sessions(
    exam_paper_id: UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(_digital_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Admin/Board/Dean: list digital exam sessions."""
    db: AsyncSession = db_info["db"]
    return await DigitalExamService.list_sessions(
        exam_paper_id=exam_paper_id, offset=offset, limit=limit, db=db
    )


@router.get("/digital/sessions/{session_id}", response_model=DigitalSessionResponse)
async def get_digital_session(
    session_id: UUID,
    current_user: CurrentUser = Depends(_digital_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Admin/Board/Dean: session detail with attempt counts."""
    db: AsyncSession = db_info["db"]
    try:
        return await DigitalExamService.get_session_detail(session_id, db=db)
    except DigitalExamError as exc:
        _raise_digital(exc)


@router.post("/digital/sessions/{session_id}/attempt", response_model=DigitalAttemptResponse, status_code=200)
async def start_or_resume_attempt(
    session_id: UUID,
    current_user: CurrentUser = Depends(_student_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Student: start or resume a digital exam attempt."""
    db: AsyncSession = db_info["db"]
    try:
        attempt = await DigitalExamService.start_or_resume_attempt(
            session_id, student_user_id=current_user.user_id, db=db
        )
    except DigitalExamError as exc:
        _raise_digital(exc)
    return DigitalAttemptResponse.model_validate(attempt)


@router.get("/digital/attempts/{attempt_id}/questions", response_model=DigitalAttemptDetailResponse)
async def get_attempt_questions(
    attempt_id: UUID,
    current_user: CurrentUser = Depends(_student_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Student: get questions for current attempt (no correct answers exposed)."""
    db: AsyncSession = db_info["db"]
    try:
        return await DigitalExamService.get_attempt_with_questions(
            attempt_id, student_user_id=current_user.user_id, db=db
        )
    except DigitalExamError as exc:
        _raise_digital(exc)


@router.put(
    "/digital/attempts/{attempt_id}/responses/{question_id}",
    response_model=DigitalResponseOut,
)
async def save_response(
    attempt_id: UUID,
    question_id: UUID,
    payload: DigitalResponseIn,
    current_user: CurrentUser = Depends(_student_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Student: save/update answer for one question (auto-save)."""
    db: AsyncSession = db_info["db"]
    try:
        return await DigitalExamService.save_response(
            attempt_id,
            question_id,
            student_user_id=current_user.user_id,
            selected_option=payload.selected_option,
            response_text=payload.response_text,
            db=db,
        )
    except DigitalExamError as exc:
        _raise_digital(exc)


@router.post("/digital/attempts/{attempt_id}/submit", response_model=DigitalResultResponse)
async def submit_attempt(
    attempt_id: UUID,
    current_user: CurrentUser = Depends(_student_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Student: submit exam — triggers MCQ auto-scoring."""
    db: AsyncSession = db_info["db"]
    try:
        return await DigitalExamService.submit_attempt(
            attempt_id, student_user_id=current_user.user_id, db=db
        )
    except DigitalExamError as exc:
        _raise_digital(exc)


@router.get("/digital/attempts/{attempt_id}/result", response_model=DigitalResultResponse)
async def get_attempt_result(
    attempt_id: UUID,
    current_user: CurrentUser = Depends(require_roles(
        TenantRole.STUDENT, TenantRole.ADMIN, TenantRole.BOARD, TenantRole.DEAN
    )),
    db_info=Depends(get_tenant_context_dep),
):
    """Student/Admin/Board: view exam result after submission."""
    db: AsyncSession = db_info["db"]
    try:
        return await DigitalExamService.get_result(
            attempt_id,
            requester_user_id=current_user.user_id,
            requester_role=current_user.role,
            db=db,
        )
    except DigitalExamError as exc:
        _raise_digital(exc)


@router.get(
    "/digital/sessions/{session_id}/analytics",
    response_model=DigitalSessionAnalyticsResponse,
)
async def get_digital_session_analytics(
    session_id: UUID,
    pass_threshold_pct: float = Query(default=40.0, ge=1.0, le=100.0),
    current_user: CurrentUser = Depends(_digital_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Dean/Admin/Board: aggregate score analytics for a session."""
    db: AsyncSession = db_info["db"]
    try:
        return await DigitalExamService.get_session_analytics(
            session_id,
            pass_threshold_pct=pass_threshold_pct,
            db=db,
        )
    except DigitalExamError as exc:
        _raise_digital(exc)


# ---------------------------------------------------------------------------
# M09.5 Phase D — Faculty Subjective Review
# ---------------------------------------------------------------------------

@router.get(
    "/digital/sessions/{session_id}/attempts/pending-review",
    response_model=SubjectiveQueueResponse,
)
async def list_pending_subjective_review(
    session_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit:  int = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(_faculty_review_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Faculty/Admin: list SCORED attempts that have unscored subjective responses.

    FACULTY callers are restricted to sessions whose exam paper belongs to a
    course they are assigned to (or created).  ADMIN sees all sessions.
    """
    db: AsyncSession = db_info["db"]
    try:
        return await DigitalExamService.list_pending_subjective_review(
            session_id,
            faculty_user_id=current_user.user_id,
            faculty_role=current_user.role,
            offset=offset,
            limit=limit,
            db=db,
        )
    except DigitalExamError as exc:
        _raise_digital(exc)


@router.get(
    "/digital/attempts/{attempt_id}/subjective-responses",
    response_model=SubjectiveReviewResponse,
)
async def get_subjective_responses(
    attempt_id: UUID,
    current_user: CurrentUser = Depends(_faculty_review_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Faculty/Admin: view all subjective questions + student answers for one attempt.

    Valid only when attempt status is SCORED or FULLY_EVALUATED.
    Includes question text, max_marks, student response, and any faculty score already saved.
    """
    db: AsyncSession = db_info["db"]
    try:
        return await DigitalExamService.get_subjective_responses(
            attempt_id,
            faculty_user_id=current_user.user_id,
            faculty_role=current_user.role,
            db=db,
        )
    except DigitalExamError as exc:
        _raise_digital(exc)


@router.patch(
    "/digital/attempts/{attempt_id}/responses/{question_id}/faculty-score",
    response_model=SubjectiveScoreOut,
)
async def save_faculty_score(
    attempt_id:  UUID,
    question_id: UUID,
    payload: FacultyScoreIn,
    current_user: CurrentUser = Depends(_faculty_review_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Faculty/Admin: save a score for one subjective response.

    Constraints: 0 ≤ score ≤ question.max_marks.
    May be called multiple times to revise a score before submission.
    Does NOT advance the attempt status — call /subjective-submit for the Gate.
    """
    db: AsyncSession = db_info["db"]
    tenant_id: UUID  = db_info["tenant_id"]
    try:
        return await DigitalExamService.save_faculty_score(
            attempt_id,
            question_id,
            score=payload.score,
            note=payload.note,
            faculty_user_id=current_user.user_id,
            faculty_role=current_user.role,
            tenant_id=tenant_id,
            db=db,
        )
    except DigitalExamError as exc:
        _raise_digital(exc)


@router.post(
    "/digital/attempts/{attempt_id}/subjective-submit",
    response_model=SubjectiveSubmitResult,
)
async def submit_subjective_scores(
    attempt_id: UUID,
    payload: SubjectiveSubmitIn,
    current_user: CurrentUser = Depends(_faculty_review_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Faculty/Admin: submit all subjective scores for one attempt (Gate).

    Pre-condition: every subjective response must have a faculty_score.
    Post-condition: attempt status → FULLY_EVALUATED (irreversible).
    Returns the MCQ auto-score, subjective total, and combined total.
    """
    db: AsyncSession = db_info["db"]
    tenant_id: UUID  = db_info["tenant_id"]
    try:
        return await DigitalExamService.submit_subjective_scores(
            attempt_id,
            submission_note=payload.submission_note,
            faculty_user_id=current_user.user_id,
            faculty_role=current_user.role,
            tenant_id=tenant_id,
            db=db,
        )
    except DigitalExamError as exc:
        _raise_digital(exc)
