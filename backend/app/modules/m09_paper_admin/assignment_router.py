"""
M09.6 Assignment Engine — Router.

Mounted at /evaluation-assignments.

RBAC
----
  _MANAGE  = ADMIN                       create / bulk / auto / cancel
  _REASSIGN= ADMIN, DEAN                 reassign + balancing
  _MONITOR = ADMIN, DEAN, BOARD          list / workload board
  _WORKER  = FACULTY, EVALUATOR, ADMIN   start / submit / complete (own work)
  _DETAIL  = ADMIN, DEAN, BOARD, FACULTY, EVALUATOR   read one (ownership-scoped)

Anonymity: every response is derived from evaluation_assignments, which stores
no student identity — only script_code / attempt_code.

Static literal paths (/me, /me/workload, /workload, /bulk, /auto) are declared
before /{assignment_id} so FastAPI routes them as literals.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth.dependencies import get_tenant_context_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m09_paper_admin.assignment_schemas import (
    AssignmentCreateRequest,
    AssignmentListResponse,
    AssignmentResponse,
    AutoAssignPreviewResponse,
    AutoAssignRequest,
    AutoAssignResultResponse,
    BulkAssignmentRequest,
    CancelRequest,
    ReassignRequest,
    WorkloadBoardResponse,
    WorkloadSummaryResponse,
)
from app.modules.m09_paper_admin.assignment_service import (
    AssignmentError,
    AssignmentService,
)

router = APIRouter(tags=["M09.6 Assignment Engine"])

_MANAGE   = [TenantRole.ADMIN]
_REASSIGN = [TenantRole.ADMIN, TenantRole.DEAN]
_MONITOR  = [TenantRole.ADMIN, TenantRole.DEAN, TenantRole.BOARD]
_WORKER   = [TenantRole.FACULTY, TenantRole.EVALUATOR, TenantRole.ADMIN]
_DETAIL   = [TenantRole.ADMIN, TenantRole.DEAN, TenantRole.BOARD,
             TenantRole.FACULTY, TenantRole.EVALUATOR]


def _manage_dep():   return require_roles(*_MANAGE)
def _reassign_dep(): return require_roles(*_REASSIGN)
def _monitor_dep():  return require_roles(*_MONITOR)
def _worker_dep():   return require_roles(*_WORKER)
def _detail_dep():   return require_roles(*_DETAIL)


def _raise(exc: AssignmentError):
    raise HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "message": exc.message},
    )


def _to_resp(row) -> AssignmentResponse:
    return AssignmentResponse.model_validate(row)


# ---------------------------------------------------------------------------
# Faculty / evaluator — own work
# ---------------------------------------------------------------------------

@router.get("/me", response_model=AssignmentListResponse)
async def my_assignments(
    status: str | None = Query(default=None),
    assignment_type: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(_worker_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """The signed-in evaluator's own assignment queue (anonymous work items)."""
    rows, total = await AssignmentService.list(
        evaluator_id=current_user.user_id,
        status=status,
        assignment_type=assignment_type,
        offset=offset,
        limit=limit,
        db=db_info["db"],
    )
    return AssignmentListResponse(
        items=[_to_resp(r) for r in rows], total=total, offset=offset, limit=limit
    )


@router.get("/me/workload", response_model=WorkloadSummaryResponse)
async def my_workload(
    current_user: CurrentUser = Depends(_worker_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    data = await AssignmentService.workload(current_user.user_id, db=db_info["db"])
    return WorkloadSummaryResponse(**data)


# ---------------------------------------------------------------------------
# Admin / Dean — workload board + listing
# ---------------------------------------------------------------------------

@router.get("/workload", response_model=WorkloadBoardResponse)
async def workload_board(
    evaluator_ids: list[UUID] = Query(default=[]),
    current_user: CurrentUser = Depends(_monitor_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Workload across a pool of evaluators (for balancing decisions)."""
    data = await AssignmentService.workload_pool(evaluator_ids, db=db_info["db"])
    return WorkloadBoardResponse(
        evaluators=[WorkloadSummaryResponse(**d) for d in data]
    )


@router.get("", response_model=AssignmentListResponse)
async def list_assignments(
    evaluator_id: UUID | None = Query(default=None),
    assignment_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    exam_paper_id: UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(_monitor_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    rows, total = await AssignmentService.list(
        evaluator_id=evaluator_id,
        assignment_type=assignment_type,
        status=status,
        exam_paper_id=exam_paper_id,
        offset=offset,
        limit=limit,
        db=db_info["db"],
    )
    return AssignmentListResponse(
        items=[_to_resp(r) for r in rows], total=total, offset=offset, limit=limit
    )


# ---------------------------------------------------------------------------
# Admin — create / bulk / auto
# ---------------------------------------------------------------------------

@router.post("", response_model=AssignmentResponse, status_code=201)
async def create_assignment(
    payload: AssignmentCreateRequest,
    current_user: CurrentUser = Depends(_manage_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    try:
        row = await AssignmentService.create_assignment(
            payload,
            assigned_by=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=db_info["tenant_id"],
            db=db_info["db"],
        )
    except AssignmentError as exc:
        _raise(exc)
    return _to_resp(row)


@router.post("/bulk", response_model=AssignmentListResponse, status_code=201)
async def bulk_assign(
    payload: BulkAssignmentRequest,
    current_user: CurrentUser = Depends(_manage_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    try:
        created, skipped = await AssignmentService.bulk_assign(
            payload,
            assigned_by=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=db_info["tenant_id"],
            db=db_info["db"],
        )
    except AssignmentError as exc:
        _raise(exc)
    return AssignmentListResponse(
        items=[_to_resp(r) for r in created],
        total=len(created),
        offset=0,
        limit=len(created),
    )


@router.post("/auto")
async def auto_assign(
    payload: AutoAssignRequest,
    current_user: CurrentUser = Depends(_manage_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Workload-balanced auto-allocation.  dry_run=True returns a preview plan
    (nothing persisted) for the Admin to ratify before committing.
    """
    try:
        result = await AssignmentService.auto_assign(
            payload,
            assigned_by=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=db_info["tenant_id"],
            db=db_info["db"],
        )
    except AssignmentError as exc:
        _raise(exc)

    if result["dry_run"]:
        return AutoAssignPreviewResponse(
            dry_run=True,
            plan=result["plan"],
            distribution=result["distribution"],
        )
    return AutoAssignResultResponse(
        dry_run=False,
        created=[_to_resp(r) for r in result["created"]],
        skipped=result["skipped"],
        distribution=result["distribution"],
    )


# ---------------------------------------------------------------------------
# Single assignment — detail + lifecycle
# ---------------------------------------------------------------------------

@router.get("/{assignment_id}", response_model=AssignmentResponse)
async def get_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_detail_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    try:
        row = await AssignmentService.get(assignment_id, db=db_info["db"])
    except AssignmentError as exc:
        _raise(exc)
    # Ownership scoping for worker roles.
    if current_user.role in ("FACULTY", "EVALUATOR") and row.evaluator_id != current_user.user_id:
        raise HTTPException(
            status_code=403,
            detail={"error": "FORBIDDEN", "message": "Not your assignment."},
        )
    return _to_resp(row)


@router.post("/{assignment_id}/start", response_model=AssignmentResponse)
async def start_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_worker_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    try:
        row = await AssignmentService.start(
            assignment_id,
            acting_user_id=current_user.user_id,
            acting_role=current_user.role,
            tenant_id=db_info["tenant_id"],
            db=db_info["db"],
        )
    except AssignmentError as exc:
        _raise(exc)
    return _to_resp(row)


@router.post("/{assignment_id}/submit", response_model=AssignmentResponse)
async def submit_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_worker_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    try:
        row = await AssignmentService.submit(
            assignment_id,
            acting_user_id=current_user.user_id,
            acting_role=current_user.role,
            tenant_id=db_info["tenant_id"],
            db=db_info["db"],
        )
    except AssignmentError as exc:
        _raise(exc)
    return _to_resp(row)


@router.post("/{assignment_id}/complete", response_model=AssignmentResponse)
async def complete_assignment(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(_worker_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    try:
        row = await AssignmentService.complete(
            assignment_id,
            acting_user_id=current_user.user_id,
            acting_role=current_user.role,
            tenant_id=db_info["tenant_id"],
            db=db_info["db"],
        )
    except AssignmentError as exc:
        _raise(exc)
    return _to_resp(row)


@router.post("/{assignment_id}/reassign", response_model=AssignmentResponse, status_code=201)
async def reassign_assignment(
    assignment_id: UUID,
    payload: ReassignRequest,
    current_user: CurrentUser = Depends(_reassign_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    try:
        row = await AssignmentService.reassign(
            assignment_id,
            payload.new_evaluator_id,
            payload.reason,
            acting_user_id=current_user.user_id,
            acting_role=current_user.role,
            tenant_id=db_info["tenant_id"],
            db=db_info["db"],
        )
    except AssignmentError as exc:
        _raise(exc)
    return _to_resp(row)


@router.post("/{assignment_id}/cancel", response_model=AssignmentResponse)
async def cancel_assignment(
    assignment_id: UUID,
    payload: CancelRequest,
    current_user: CurrentUser = Depends(_manage_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    try:
        row = await AssignmentService.cancel(
            assignment_id,
            payload.reason,
            acting_user_id=current_user.user_id,
            acting_role=current_user.role,
            tenant_id=db_info["tenant_id"],
            db=db_info["db"],
        )
    except AssignmentError as exc:
        _raise(exc)
    return _to_resp(row)
