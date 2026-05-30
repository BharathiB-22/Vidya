"""
M09 Paper Administration & Scanning — Router.

RBAC
----
  _INGEST   = ADMIN + BOARD           (upload / assign evaluator)
  _EVALUATE = FACULTY + ADMIN         (update marks / Gate 1 submit)
  _BOARD    = BOARD + ADMIN           (Gate 2 finalise / ledger read)
  _READ     = all tenant roles        (script detail / evaluations / list)

Route summary
-------------
  POST   /scripts/upload                  ingest scanned script + queue scoring
  GET    /scripts                         list all scripts (ADMIN/BOARD)
  GET    /scripts/board/pending           scripts awaiting Board finalisation
  GET    /scripts/evaluator/me            evaluator's own assigned scripts
  GET    /scripts/paper/{paper_id}        scripts for an exam paper
  GET    /scripts/{script_id}             script detail (identity masked pre-finalise)
  POST   /scripts/{script_id}/assign      assign evaluator
  PATCH  /scripts/{script_id}/marks       evaluator saves marks (no gate)
  POST   /scripts/{script_id}/submit      Gate 1: evaluator submits all marks
  POST   /scripts/{script_id}/finalise    Gate 2: Board finalises + writes ledger
  GET    /scripts/{script_id}/evaluations AI suggestions + evaluator marks
  GET    /scripts/{script_id}/ledger      Board-finalised score record

Static paths (/board/pending, /evaluator/me, /paper/...) are declared before
/{script_id} so FastAPI routes them as literals, not path parameters.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_context_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m09_paper_admin.schemas import (
    AcceptSuggestionsRequest,
    BulkMarkUpdate,
    EvaluatorReviewResponse,
    ExamScoreLedgerListResponse,
    ExamScoreLedgerResponse,
    JobStatusResponse,
    PaperPipelineStats,
    ScannedScriptListResponse,
    ScannedScriptResponse,
    ScriptAssignEvaluatorRequest,
    ScriptEvaluationResponse,
    ScriptFinaliseRequest,
    ScriptIngestRequest,
    ScriptSubmitMarksRequest,
)
from app.modules.m09_paper_admin.service import ScriptService, ScriptServiceError

router = APIRouter(tags=["M09 Paper Admin"])

# ---------------------------------------------------------------------------
# Role groups
# ---------------------------------------------------------------------------

_INGEST   = [TenantRole.ADMIN, TenantRole.BOARD]
_EVALUATE = [TenantRole.FACULTY, TenantRole.ADMIN]
_BOARD    = [TenantRole.BOARD, TenantRole.ADMIN]
_READ     = [TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY, TenantRole.BOARD]


def _ingest_dep():   return require_roles(*_INGEST)
def _eval_dep():     return require_roles(*_EVALUATE)
def _board_dep():    return require_roles(*_BOARD)
def _read_dep():     return require_roles(*_READ)


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------

def _raise(exc: ScriptServiceError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "message": exc.message},
    )


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
