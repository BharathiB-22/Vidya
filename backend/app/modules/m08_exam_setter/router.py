"""
M08 Exam Setter — Router.

RBAC
----
  _FACULTY  = ADMIN + FACULTY          (create, edit, submit, seal)
  _BOARD    = BOARD + ADMIN            (board review + decision)
  _READ     = ADMIN + DEAN + FACULTY + BOARD

Endpoint summary (faculty)
--------------------------
  POST   /exams                         create paper config + queue generation
  GET    /exams                         list papers for authenticated faculty
  GET    /exams/all                     admin/dean: all papers for tenant
  GET    /exams/{id}                    paper detail (questions blocked if SEALED)
  GET    /exams/{id}/questions          list questions (no model answers)
  PATCH  /exams/{id}/questions/{q_id}   edit one question
  DELETE /exams/{id}/questions/{q_id}   remove one question
  GET    /exams/{id}/blooms             Bloom's compliance report
  POST   /exams/{id}/submit             Gate 1: submit for Board review
  POST   /exams/{id}/seal               Gate 3: seal paper

Endpoint summary (board)
------------------------
  GET    /exams/board/pending           papers awaiting Board review
  POST   /exams/{id}/board-decision     Gate 2: approve or return

Export (role-gated, post-release)
----------------------------------
  GET    /exams/{id}/export/questions   question paper PDF (FACULTY/BOARD/ADMIN/STUDENT)
  GET    /exams/{id}/export/answers     model answers PDF (FACULTY/BOARD/ADMIN only)

Common
------
  GET    /jobs/{job_id}                 poll job status
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.dependencies import get_tenant_context_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m08_exam_setter.schemas import (
    BloomsComplianceResponse,
    BoardDecisionRequest,
    ExamPaperCreate,
    ExamPaperListResponse,
    ExamPaperResponse,
    ExamQuestionResponse,
    ExamQuestionUpdate,
    ExamQuestionWithAnswerResponse,
    JobStatusResponse,
    SealRequest,
)
from app.modules.m08_exam_setter.service import ExamService, ExamServiceError

router = APIRouter(tags=["M08 Exam Setter"])

# ---------------------------------------------------------------------------
# Role groups
# ---------------------------------------------------------------------------

_FACULTY = [TenantRole.ADMIN, TenantRole.FACULTY]
_BOARD   = [TenantRole.BOARD, TenantRole.ADMIN]
_READ    = [TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY, TenantRole.BOARD]


def _faculty_dep():
    return require_roles(*_FACULTY)


def _board_dep():
    return require_roles(*_BOARD)


def _read_dep():
    return require_roles(*_READ)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _raise(exc: ExamServiceError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "message": exc.message},
    )


# ---------------------------------------------------------------------------
# Create paper
# ---------------------------------------------------------------------------

@router.post("", response_model=dict, status_code=202)
async def create_exam_paper(
    payload: ExamPaperCreate,
    current_user: CurrentUser = Depends(_faculty_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Create an exam paper configuration and queue AI question generation."""
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        paper, job_id = await ExamService.create(
            payload,
            created_by=current_user.user_id,
            tenant_id=tenant_id,
            schema_name=schema,
            db=db,
        )
    except ExamServiceError as exc:
        _raise(exc)

    await AuditService.log(
        AuditEventType.EXAM_PAPER_CREATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_paper",
        target_id=str(paper.id),
        metadata={"title": paper.title, "total_marks": paper.total_marks},
    )
    await AuditService.log(
        AuditEventType.EXAM_PAPER_GENERATION_QUEUED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_paper",
        target_id=str(paper.id),
        metadata={"job_id": str(job_id)},
    )

    return {"paper_id": str(paper.id), "job_id": str(job_id), "status": paper.status}


# ---------------------------------------------------------------------------
# List papers — faculty own
# ---------------------------------------------------------------------------

@router.get("", response_model=ExamPaperListResponse)
async def list_exam_papers(
    status:  str | None = Query(default=None),
    offset:  int        = Query(default=0, ge=0),
    limit:   int        = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(_faculty_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """List exam papers created by the authenticated faculty member."""
    db: AsyncSession = db_info["db"]

    papers = await ExamService.list_for_faculty(
        current_user.user_id, status=status, offset=offset, limit=limit, db=db
    )
    return ExamPaperListResponse(
        items=[ExamPaperResponse.model_validate(p) for p in papers],
        total=len(papers),
        offset=offset,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# List all papers — admin / dean
# ---------------------------------------------------------------------------

@router.get("/all", response_model=ExamPaperListResponse)
async def list_all_exam_papers(
    status:  str | None = Query(default=None),
    offset:  int        = Query(default=0, ge=0),
    limit:   int        = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Admin/Dean: list all exam papers for the tenant."""
    db: AsyncSession = db_info["db"]

    papers = await ExamService.list_all(status=status, offset=offset, limit=limit, db=db)
    return ExamPaperListResponse(
        items=[ExamPaperResponse.model_validate(p) for p in papers],
        total=len(papers),
        offset=offset,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Board: pending papers
# ---------------------------------------------------------------------------

@router.get("/board/pending", response_model=ExamPaperListResponse)
async def list_board_pending(
    offset: int = Query(default=0, ge=0),
    limit:  int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Examination Board: list papers awaiting review."""
    db: AsyncSession = db_info["db"]

    papers = await ExamService.list_board_pending(offset=offset, limit=limit, db=db)
    return ExamPaperListResponse(
        items=[ExamPaperResponse.model_validate(p) for p in papers],
        total=len(papers),
        offset=offset,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Paper detail
# ---------------------------------------------------------------------------

@router.get("/{paper_id}", response_model=ExamPaperResponse)
async def get_exam_paper(
    paper_id: UUID,
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Get exam paper metadata. Questions not included here — use /questions endpoint."""
    db: AsyncSession = db_info["db"]
    try:
        paper = await ExamService.get(paper_id, db=db)
    except ExamServiceError as exc:
        _raise(exc)
    return ExamPaperResponse.model_validate(paper)


# ---------------------------------------------------------------------------
# Questions list
# ---------------------------------------------------------------------------

@router.get("/{paper_id}/questions", response_model=list[ExamQuestionResponse])
async def list_questions(
    paper_id:  UUID,
    set_label: str | None = Query(default=None, description="Filter by set: A or B"),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    List questions for a paper. Model answers excluded.
    Returns 403 if paper is SEALED.
    """
    db: AsyncSession = db_info["db"]
    try:
        questions = await ExamService.get_questions(
            paper_id, set_label=set_label, include_answers=False, db=db
        )
    except ExamServiceError as exc:
        _raise(exc)
    return [ExamQuestionResponse.model_validate(q) for q in questions]


# ---------------------------------------------------------------------------
# Edit question
# ---------------------------------------------------------------------------

@router.patch("/{paper_id}/questions/{question_id}", response_model=ExamQuestionResponse)
async def edit_question(
    paper_id:    UUID,
    question_id: UUID,
    payload:     ExamQuestionUpdate,
    current_user: CurrentUser = Depends(_faculty_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Faculty edits a question. Only allowed when paper is GENERATED or BOARD_RETURNED."""
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        question = await ExamService.update_question(
            paper_id, question_id, payload,
            editor_user_id=current_user.user_id,
            db=db,
        )
    except ExamServiceError as exc:
        _raise(exc)

    await AuditService.log(
        AuditEventType.EXAM_PAPER_QUESTION_EDITED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_question",
        target_id=str(question_id),
        metadata={"exam_paper_id": str(paper_id)},
    )
    return ExamQuestionResponse.model_validate(question)


# ---------------------------------------------------------------------------
# Delete question
# ---------------------------------------------------------------------------

@router.delete("/{paper_id}/questions/{question_id}", status_code=204)
async def delete_question(
    paper_id:    UUID,
    question_id: UUID,
    current_user: CurrentUser = Depends(_faculty_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Faculty removes a question from the paper."""
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        await ExamService.delete_question(paper_id, question_id, db=db)
    except ExamServiceError as exc:
        _raise(exc)

    await AuditService.log(
        AuditEventType.EXAM_PAPER_QUESTION_REPLACED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_question",
        target_id=str(question_id),
        metadata={"exam_paper_id": str(paper_id), "action": "deleted"},
    )


# ---------------------------------------------------------------------------
# Bloom's compliance report
# ---------------------------------------------------------------------------

@router.get("/{paper_id}/blooms", response_model=BloomsComplianceResponse)
async def get_blooms_report(
    paper_id: UUID,
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Get Bloom's compliance report for a paper."""
    db: AsyncSession = db_info["db"]
    try:
        report = await ExamService.get_blooms_report(paper_id, db=db)
    except ExamServiceError as exc:
        _raise(exc)
    return BloomsComplianceResponse.model_validate(report)


# ---------------------------------------------------------------------------
# GATE 1 — Faculty submits for Board review
# ---------------------------------------------------------------------------

@router.post("/{paper_id}/submit", response_model=ExamPaperResponse)
async def submit_for_review(
    paper_id: UUID,
    current_user: CurrentUser = Depends(_faculty_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """GATE 1: Faculty submits paper for Examination Board review."""
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        paper = await ExamService.submit_for_review(
            paper_id, faculty_user_id=current_user.user_id, db=db
        )
    except ExamServiceError as exc:
        _raise(exc)

    await AuditService.log(
        AuditEventType.EXAM_PAPER_SUBMITTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_paper",
        target_id=str(paper_id),
        metadata={"title": paper.title},
    )
    return ExamPaperResponse.model_validate(paper)


# ---------------------------------------------------------------------------
# GATE 2 — Board decision
# ---------------------------------------------------------------------------

@router.post("/{paper_id}/board-decision", response_model=ExamPaperResponse)
async def board_decision(
    paper_id: UUID,
    payload:  BoardDecisionRequest,
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """GATE 2: Examination Board approves or returns the paper."""
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        paper = await ExamService.board_decide(
            paper_id, payload, board_user_id=current_user.user_id, db=db
        )
    except ExamServiceError as exc:
        _raise(exc)

    event = (
        AuditEventType.EXAM_PAPER_BOARD_APPROVED
        if payload.approved
        else AuditEventType.EXAM_PAPER_BOARD_RETURNED
    )
    await AuditService.log(
        event,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_paper",
        target_id=str(paper_id),
        metadata={"approved": payload.approved, "board_comment": payload.board_comment},
    )
    return ExamPaperResponse.model_validate(paper)


# ---------------------------------------------------------------------------
# GATE 3 — Faculty seals paper
# ---------------------------------------------------------------------------

@router.post("/{paper_id}/seal", response_model=ExamPaperResponse)
async def seal_paper(
    paper_id: UUID,
    payload:  SealRequest,
    current_user: CurrentUser = Depends(_faculty_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """GATE 3: Faculty seals the paper with AES encryption and schedules release."""
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        paper = await ExamService.seal(
            paper_id,
            payload,
            faculty_user_id=current_user.user_id,
            tenant_id=tenant_id,
            schema_name=schema,
            db=db,
        )
    except ExamServiceError as exc:
        _raise(exc)

    await AuditService.log(
        AuditEventType.EXAM_PAPER_SEALED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_paper",
        target_id=str(paper_id),
        metadata={"release_at": payload.release_at.isoformat(), "title": paper.title},
    )
    return ExamPaperResponse.model_validate(paper)


# ---------------------------------------------------------------------------
# Export — question paper (role-gated: RELEASED required)
# ---------------------------------------------------------------------------

@router.get("/{paper_id}/export/questions")
async def export_questions(
    paper_id:  UUID,
    set_label: str = Query(default="A", description="Set A or B"),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Export question paper as PDF.
    Paper must be RELEASED. No model answers included.
    STUDENT role may download questions only.
    """
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        paper = await ExamService.get(paper_id, db=db)
    except ExamServiceError as exc:
        _raise(exc)

    from app.modules.m08_exam_setter.models import ExamPaperStatus
    if paper.status != ExamPaperStatus.RELEASED.value:
        raise HTTPException(
            status_code=403,
            detail={"error": "NOT_RELEASED", "message": "Exam paper is not yet released."},
        )

    questions = await ExamService.get_questions(
        paper_id, set_label=set_label, include_answers=False, db=db
    )

    await AuditService.log(
        AuditEventType.EXAM_PAPER_EXPORTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_paper",
        target_id=str(paper_id),
        metadata={"export_type": "questions", "set_label": set_label},
    )

    # Return questions as JSON (PDF generation is a future enhancement)
    return {
        "paper_id":    str(paper_id),
        "title":       paper.title,
        "set_label":   set_label,
        "total_marks": paper.total_marks,
        "questions":   [ExamQuestionResponse.model_validate(q).model_dump() for q in questions],
    }


# ---------------------------------------------------------------------------
# Export — model answers (FACULTY/BOARD/ADMIN only, post-release)
# ---------------------------------------------------------------------------

@router.get("/{paper_id}/export/answers")
async def export_answers(
    paper_id:  UUID,
    set_label: str = Query(default="A", description="Set A or B"),
    current_user: CurrentUser = Depends(require_roles(*(_BOARD + [TenantRole.FACULTY]))),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Export model answers PDF. FACULTY/BOARD/ADMIN only. Never exposed to students.
    Paper must be RELEASED.
    """
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        paper = await ExamService.get(paper_id, db=db)
    except ExamServiceError as exc:
        _raise(exc)

    from app.modules.m08_exam_setter.models import ExamPaperStatus
    if paper.status != ExamPaperStatus.RELEASED.value:
        raise HTTPException(
            status_code=403,
            detail={"error": "NOT_RELEASED", "message": "Exam paper is not yet released."},
        )

    questions = await ExamService.get_questions(
        paper_id, set_label=set_label, include_answers=True, db=db
    )

    await AuditService.log(
        AuditEventType.EXAM_PAPER_EXPORTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_paper",
        target_id=str(paper_id),
        metadata={"export_type": "answers", "set_label": set_label},
    )

    return {
        "paper_id":    str(paper_id),
        "title":       paper.title,
        "set_label":   set_label,
        "total_marks": paper.total_marks,
        "questions":   [ExamQuestionWithAnswerResponse.model_validate(q).model_dump() for q in questions],
    }


# ---------------------------------------------------------------------------
# Job status polling
# ---------------------------------------------------------------------------

@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: UUID,
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Poll Celery task job status."""
    from sqlalchemy import text as sa_text
    from app.database import async_session_public

    async with async_session_public() as pub_db:
        result = await pub_db.execute(
            sa_text("SELECT id, status, result FROM public.task_jobs WHERE id = :id"),
            {"id": str(job_id)},
        )
        row = result.mappings().one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Job not found."})

    import json as _json
    result_data = None
    if row["result"]:
        try:
            result_data = _json.loads(row["result"]) if isinstance(row["result"], str) else row["result"]
        except Exception:
            result_data = {"raw": str(row["result"])}

    return JobStatusResponse(job_id=job_id, status=row["status"], result=result_data)
