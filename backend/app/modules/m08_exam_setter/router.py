"""
M08 Exam Setter — Router.

RBAC
----
  _CREATE   = ADMIN + FACULTY + BOARD  (create paper)
  _FACULTY  = ADMIN + FACULTY          (edit questions, submit, approve)
  _BOARD    = BOARD + ADMIN            (review, approve/return, seal, release, assign scrutinizer)
  _DEAN     = DEAN + ADMIN             (lock internal marks)
  _READ     = ADMIN + DEAN + FACULTY + BOARD

Workflow (BOARD_EXAM): Faculty creates → submits (Gate 1) → [scrutinizer review (1.5)] →
  Board approves/returns (Gate 2) → Board seals (Gate 3) → auto-release.

Workflow (INTERNAL):   Faculty creates → faculty_approve (Gate 1) → Faculty seals → auto-release.

Endpoint summary (faculty)
--------------------------
  POST   /exams                              create paper + queue generation
  GET    /exams                              list papers for authenticated faculty
  GET    /exams/all                          admin/dean: all papers for tenant
  GET    /exams/{id}                         paper detail
  GET    /exams/{id}/questions               list questions (no model answers)
  PATCH  /exams/{id}/questions/{q_id}        edit one question
  DELETE /exams/{id}/questions/{q_id}        remove one question
  POST   /exams/{id}/questions/{q_id}/regenerate  re-generate single question (STEP-8)
  GET    /exams/{id}/blooms                  Bloom's compliance report
  GET    /exams/{id}/coverage                CO + unit coverage report
  POST   /exams/{id}/submit                  Gate 1 (BOARD_EXAM): submit for Board review
  POST   /exams/{id}/faculty-approve         Gate 1 (INTERNAL): faculty self-approve
  PUT    /exams/{id}/sections                update section configuration

Endpoint summary (board / scrutinizer)
---------------------------------------
  GET    /exams/board/pending                papers awaiting Board review
  POST   /exams/{id}/assign-scrutinizer      assign scrutinizer (BOARD_EXAM, Gate 1.5)
  POST   /exams/{id}/scrutinize             scrutinizer approve/return (Gate 1.5)
  POST   /exams/{id}/board-decision         Gate 2: approve or return
  POST   /exams/{id}/seal                   Gate 3: seal paper
  POST   /exams/{id}/release                immediate release (BOARD/ADMIN)

Question bank
-------------
  GET    /exams/question-bank/{course_id}    browse approved question bank entries

Internal marks
--------------
  POST   /exams/internal-marks               create / update marks entry (FACULTY)
  GET    /exams/internal-marks/{id}          get single record (_READ)
  PATCH  /exams/internal-marks/{id}          update marks components (FACULTY)
  GET    /exams/internal-marks/course/{cid}  list by course (_READ)
  POST   /exams/internal-marks/{id}/submit   Gate 1: faculty submits
  POST   /exams/internal-marks/{id}/lock     Gate 2: Dean locks

Export (role-gated, post-release)
----------------------------------
  GET    /exams/{id}/export/questions        question paper (FACULTY/BOARD/ADMIN/STUDENT)
  GET    /exams/{id}/export/answers          model answers (FACULTY/BOARD/ADMIN only)

Common
------
  GET    /jobs/{job_id}                      poll job status
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.dependencies import get_tenant_context_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.rate_limiting import limiter
from app.modules.m08_exam_setter.schemas import (
    BloomsComplianceResponse,
    BoardDecisionRequest,
    ExamPaperCreate,
    ExamPaperListResponse,
    ExamPaperResponse,
    ExamQuestionResponse,
    ExamQuestionUpdate,
    ExamQuestionWithAnswerResponse,
    FacultyApproveRequest,
    InternalMarksCreate,
    InternalMarksListResponse,
    InternalMarksResponse,
    InternalMarksUpdate,
    JobStatusResponse,
    QuestionBankListResponse,
    QuestionBankEntryResponse,
    RegenerateQuestionRequest,
    ScrutinizerAssignRequest,
    ScrutinizerDecisionRequest,
    SealRequest,
    SectionConfig,
)
from app.modules.m08_exam_setter.service import (
    ExamService,
    ExamServiceError,
    InternalMarksService,
    InternalMarksServiceError,
)

router = APIRouter(tags=["M08 Exam Setter"])
logger = logging.getLogger("vidya.router.m08")

# ---------------------------------------------------------------------------
# Role groups
# ---------------------------------------------------------------------------

_CREATE  = [TenantRole.ADMIN, TenantRole.FACULTY, TenantRole.BOARD]
_FACULTY = [TenantRole.ADMIN, TenantRole.FACULTY]
_BOARD   = [TenantRole.BOARD, TenantRole.ADMIN]
_DEAN    = [TenantRole.DEAN, TenantRole.ADMIN]
_READ    = [TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY, TenantRole.BOARD]


def _create_dep():
    return require_roles(*_CREATE)


def _faculty_dep():
    return require_roles(*_FACULTY)


def _board_dep():
    return require_roles(*_BOARD)


def _dean_dep():
    return require_roles(*_DEAN)


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


def _raise_ims(exc: InternalMarksServiceError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "message": exc.message},
    )


# ---------------------------------------------------------------------------
# Create paper
# ---------------------------------------------------------------------------

@router.post("", response_model=dict, status_code=202)
@limiter.limit("5/minute")
async def create_exam_paper(
    request: Request,
    payload: ExamPaperCreate,
    current_user: CurrentUser = Depends(_create_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Create an exam paper and queue AI generation. FACULTY (course papers) and BOARD (official END SEM papers) may create."""
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
    except Exception as exc:
        logger.exception("ExamService.create failed for tenant %s: %s", tenant_id, exc)
        detail = str(exc) if settings.ENVIRONMENT == "development" else "An unexpected error occurred"
        raise HTTPException(status_code=500, detail={"error": "INTERNAL_ERROR", "message": detail})

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
    except Exception as exc:
        logger.exception(
            "list_questions failed for paper=%s set_label=%r: %s",
            paper_id, set_label, exc,
        )
        detail = str(exc) if settings.ENVIRONMENT == "development" else "Failed to load questions"
        raise HTTPException(status_code=500, detail={"error": "INTERNAL_ERROR", "message": detail})

    logger.debug(
        "list_questions paper=%s set_label=%r → %d questions",
        paper_id, set_label, len(questions),
    )
    try:
        return [ExamQuestionResponse.model_validate(q) for q in questions]
    except Exception as exc:
        logger.exception(
            "ExamQuestionResponse serialization failed for paper=%s: %s",
            paper_id, exc,
        )
        detail = str(exc) if settings.ENVIRONMENT == "development" else "Question serialization error"
        raise HTTPException(status_code=500, detail={"error": "SERIALIZATION_ERROR", "message": detail})


# ---------------------------------------------------------------------------
# Board review — questions with model answers (H-35 STEP-11)
# ---------------------------------------------------------------------------

@router.get("/{paper_id}/questions/with-answers", response_model=list[ExamQuestionWithAnswerResponse])
async def list_questions_with_answers(
    paper_id:  UUID,
    set_label: str | None = Query(default=None, description="Filter by set: A or B"),
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Questions with model answers, marking schemes, and correct options.
    BOARD/ADMIN only. Paper must be SUBMITTED or later.
    """
    db: AsyncSession = db_info["db"]

    try:
        paper = await ExamService.get(paper_id, db=db)
    except ExamServiceError as exc:
        _raise(exc)

    from app.modules.m08_exam_setter.models import ExamPaperStatus
    allowed = {
        ExamPaperStatus.SUBMITTED.value,
        ExamPaperStatus.BOARD_APPROVED.value,
        ExamPaperStatus.BOARD_RETURNED.value,
        ExamPaperStatus.SEALED.value,
        ExamPaperStatus.RELEASED.value,
    }
    if paper.status not in allowed:
        raise HTTPException(
            status_code=403,
            detail={"error": "NOT_SUBMITTED", "message": "Model answers are only available for submitted or later papers."},
        )

    try:
        questions = await ExamService.get_questions(
            paper_id, set_label=set_label, include_answers=True, db=db
        )
    except ExamServiceError as exc:
        _raise(exc)

    return [ExamQuestionWithAnswerResponse.model_validate(q) for q in questions]


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
# GATE 3 — Board seals paper
# ---------------------------------------------------------------------------

@router.post("/{paper_id}/seal", response_model=ExamPaperResponse)
async def seal_paper(
    paper_id: UUID,
    payload:  SealRequest,
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """GATE 3: Board seals the paper with AES encryption and schedules auto-release."""
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        paper = await ExamService.seal(
            paper_id,
            payload,
            sealing_user_id=current_user.user_id,
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
# Board: immediate release
# ---------------------------------------------------------------------------

@router.post("/{paper_id}/release", response_model=ExamPaperResponse)
async def release_paper(
    paper_id: UUID,
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Board immediately releases a sealed paper (bypasses scheduled release_at time)."""
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        paper = await ExamService.force_release(paper_id, schema_name=schema, db=db)
    except ExamServiceError as exc:
        _raise(exc)

    await AuditService.log(
        AuditEventType.EXAM_PAPER_RELEASED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_paper",
        target_id=str(paper_id),
        metadata={"title": paper.title, "released_by": str(current_user.user_id)},
    )
    return ExamPaperResponse.model_validate(paper)


# ---------------------------------------------------------------------------
# H-35: INTERNAL workflow — faculty self-approval (Gate 1)
# ---------------------------------------------------------------------------

@router.post("/{paper_id}/faculty-approve", response_model=ExamPaperResponse)
async def faculty_approve(
    paper_id: UUID,
    payload:  FacultyApproveRequest,
    current_user: CurrentUser = Depends(_faculty_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    GATE 1 (INTERNAL workflow only): Faculty self-approves the paper.
    Transitions GENERATED → BOARD_APPROVED, skipping Board review.
    Use submit + board-decision for BOARD_EXAM papers.
    """
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        paper = await ExamService.faculty_approve(
            paper_id, payload, faculty_user_id=current_user.user_id, db=db
        )
    except ExamServiceError as exc:
        _raise(exc)

    await AuditService.log(
        AuditEventType.EXAM_PAPER_FACULTY_APPROVED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_paper",
        target_id=str(paper_id),
        metadata={"title": paper.title, "faculty_comment": payload.faculty_comment},
    )
    return ExamPaperResponse.model_validate(paper)


# ---------------------------------------------------------------------------
# H-35: Section configuration (faculty)
# ---------------------------------------------------------------------------

@router.put("/{paper_id}/sections", response_model=ExamPaperResponse)
async def configure_sections(
    paper_id: UUID,
    sections: list[SectionConfig],
    current_user: CurrentUser = Depends(_faculty_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Update Part A/B/C section configuration. Only valid before submission."""
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        paper = await ExamService.configure_sections(
            paper_id,
            [s.model_dump() for s in sections],
            faculty_user_id=current_user.user_id,
            db=db,
        )
    except ExamServiceError as exc:
        _raise(exc)

    await AuditService.log(
        AuditEventType.EXAM_PAPER_SECTION_CONFIGURED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_paper",
        target_id=str(paper_id),
        metadata={"section_count": len(sections)},
    )
    return ExamPaperResponse.model_validate(paper)


# ---------------------------------------------------------------------------
# H-35: CO + unit coverage report
# ---------------------------------------------------------------------------

@router.get("/{paper_id}/coverage")
async def get_coverage_report(
    paper_id: UUID,
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Return the CO and unit coverage report generated during paper creation."""
    db: AsyncSession = db_info["db"]

    try:
        paper = await ExamService.get(paper_id, db=db)
    except ExamServiceError as exc:
        _raise(exc)

    return {
        "paper_id":            str(paper_id),
        "exam_workflow":       paper.exam_workflow,
        "co_coverage_report":  paper.co_coverage_report,
        "unit_coverage_report": paper.unit_coverage_report,
    }


# ---------------------------------------------------------------------------
# H-35: Scrutinizer — assign (BOARD only) and decide (FACULTY/ADMIN)
# ---------------------------------------------------------------------------

@router.post("/{paper_id}/assign-scrutinizer", response_model=ExamPaperResponse)
async def assign_scrutinizer(
    paper_id: UUID,
    payload:  ScrutinizerAssignRequest,
    current_user: CurrentUser = Depends(_board_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """BOARD_EXAM only: assign a second-faculty scrutinizer to a SUBMITTED paper."""
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        paper = await ExamService.assign_scrutinizer(
            paper_id, payload, assigning_user_id=current_user.user_id, db=db
        )
    except ExamServiceError as exc:
        _raise(exc)

    await AuditService.log(
        AuditEventType.EXAM_PAPER_SCRUTINIZER_ASSIGNED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_paper",
        target_id=str(paper_id),
        metadata={"scrutinizer_id": str(payload.scrutinizer_id)},
    )
    return ExamPaperResponse.model_validate(paper)


@router.post("/{paper_id}/scrutinize", response_model=ExamPaperResponse)
async def scrutinize(
    paper_id: UUID,
    payload:  ScrutinizerDecisionRequest,
    current_user: CurrentUser = Depends(_faculty_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Gate 1.5 (BOARD_EXAM): Assigned scrutinizer approves or returns the paper.
    Approved: paper stays SUBMITTED for Board. Returned: paper reverts to BOARD_RETURNED.
    """
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        paper = await ExamService.scrutinize(
            paper_id, payload, scrutinizer_user_id=current_user.user_id, db=db
        )
    except ExamServiceError as exc:
        _raise(exc)

    await AuditService.log(
        AuditEventType.EXAM_PAPER_SCRUTINIZED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_paper",
        target_id=str(paper_id),
        metadata={"approved": payload.approved, "comment": payload.scrutinizer_comment},
    )
    return ExamPaperResponse.model_validate(paper)


# ---------------------------------------------------------------------------
# H-35: Single-question regeneration
# ---------------------------------------------------------------------------

@router.post("/{paper_id}/questions/{question_id}/regenerate", status_code=202)
async def regenerate_question(
    paper_id:    UUID,
    question_id: UUID,
    payload:     RegenerateQuestionRequest,
    current_user: CurrentUser = Depends(_faculty_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Faculty re-generates a single question asynchronously.
    The paper must be GENERATED or BOARD_RETURNED.
    Returns 202 immediately; poll /jobs/{job_id} for completion.
    """
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        paper = await ExamService.get(paper_id, db=db)
    except ExamServiceError as exc:
        _raise(exc)

    from app.modules.m08_exam_setter.models import ExamPaperStatus
    editable = (ExamPaperStatus.GENERATED.value, ExamPaperStatus.BOARD_RETURNED.value)
    if paper.status not in editable:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_STATUS",
                "message": (
                    f"Regeneration only allowed when paper is GENERATED or BOARD_RETURNED "
                    f"(current: {paper.status!r})."
                ),
            },
        )

    # Validate the question belongs to this paper before queuing
    from app.modules.m08_exam_setter.repository import ExamQuestionRepository
    question = await ExamQuestionRepository.get_by_id(question_id, db=db)
    if question is None or question.exam_paper_id != paper_id:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "message": "Question not found on this paper."},
        )

    # Create task_job record and dispatch worker
    from app.database import AsyncSessionLocal
    from app.modules.m08_exam_setter.repository import TaskJobPublicRepository

    async with AsyncSessionLocal() as pub_db:
        job_id = await TaskJobPublicRepository.create(
            task_type="regenerate_exam_question",
            queue_name="heavy",
            tenant_id=tenant_id,
            payload={
                "paper_id":    str(paper_id),
                "question_id": str(question_id),
                "schema_name": schema,
                "instruction": payload.instruction,
            },
            db=pub_db,
        )
        await pub_db.commit()

    try:
        from app.workers.heavy.regenerate_exam_question import regenerate_exam_question
        regenerate_exam_question.apply_async(
            kwargs={
                "job_id":      str(job_id),
                "paper_id":    str(paper_id),
                "question_id": str(question_id),
                "schema_name": schema,
                "instruction": payload.instruction,
            }
        )
    except Exception as exc:
        logger.error(
            "Failed to dispatch regenerate task for question %s paper %s: %s",
            question_id, paper_id, exc,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "QUEUE_UNAVAILABLE",
                "message": (
                    "Regeneration could not be queued — the task worker appears to be offline. "
                    "Start the Celery worker and try again."
                ),
            },
        )

    await AuditService.log(
        AuditEventType.EXAM_PAPER_QUESTION_REGENERATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_question",
        target_id=str(question_id),
        metadata={
            "exam_paper_id": str(paper_id),
            "job_id":        str(job_id),
            "instruction":   payload.instruction,
        },
    )

    return {
        "paper_id":    str(paper_id),
        "question_id": str(question_id),
        "job_id":      str(job_id),
        "status":      "QUEUED",
    }


# ---------------------------------------------------------------------------
# H-35: Question bank browse
# ---------------------------------------------------------------------------

@router.get("/question-bank/{course_id}", response_model=QuestionBankListResponse)
async def list_question_bank(
    course_id:     UUID,
    bloom_level:   str | None = Query(default=None),
    question_type: str | None = Query(default=None),
    unit_number:   int | None = Query(default=None),
    offset:        int        = Query(default=0, ge=0),
    limit:         int        = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Browse approved question bank entries for a course."""
    db: AsyncSession = db_info["db"]

    items, total = await ExamService.list_question_bank(
        course_id,
        bloom_level=bloom_level,
        question_type=question_type,
        unit_number=unit_number,
        offset=offset,
        limit=limit,
        db=db,
    )
    return QuestionBankListResponse(
        items=[QuestionBankEntryResponse.model_validate(e) for e in items],
        total=total,
        offset=offset,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# H-35: Internal marks — create / update (FACULTY)
# ---------------------------------------------------------------------------

@router.post("/internal-marks", response_model=InternalMarksResponse, status_code=201)
async def create_internal_marks(
    payload: InternalMarksCreate,
    current_user: CurrentUser = Depends(_faculty_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Create or update an internal marks record for a student/course/semester.
    If a PENDING record already exists it is updated; DEAN_LOCKED records are rejected.
    """
    db: AsyncSession = db_info["db"]

    try:
        ims = await InternalMarksService.create_or_update(
            payload, faculty_user_id=current_user.user_id, db=db
        )
    except InternalMarksServiceError as exc:
        _raise_ims(exc)

    return InternalMarksResponse.model_validate(ims)


@router.get("/internal-marks/course/{course_id}", response_model=InternalMarksListResponse)
async def list_internal_marks_by_course(
    course_id:     UUID,
    semester:      int | None = Query(default=None),
    academic_year: str | None = Query(default=None),
    offset:        int        = Query(default=0, ge=0),
    limit:         int        = Query(default=100, ge=1, le=500),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """List internal marks records for a course, optionally filtered by semester/year."""
    db: AsyncSession = db_info["db"]

    items, total = await InternalMarksService.list_by_course(
        course_id,
        semester=semester,
        academic_year=academic_year,
        offset=offset,
        limit=limit,
        db=db,
    )
    return InternalMarksListResponse(
        items=[InternalMarksResponse.model_validate(i) for i in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/internal-marks/{ims_id}", response_model=InternalMarksResponse)
async def get_internal_marks(
    ims_id: UUID,
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Get a single internal marks record by ID."""
    db: AsyncSession = db_info["db"]

    try:
        ims = await InternalMarksService.get(ims_id, db=db)
    except InternalMarksServiceError as exc:
        _raise_ims(exc)

    return InternalMarksResponse.model_validate(ims)


@router.patch("/internal-marks/{ims_id}", response_model=InternalMarksResponse)
async def update_internal_marks(
    ims_id:  UUID,
    payload: InternalMarksUpdate,
    current_user: CurrentUser = Depends(_faculty_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """Update mark components on a PENDING internal marks record."""
    db: AsyncSession = db_info["db"]

    try:
        ims = await InternalMarksService.update(ims_id, payload, db=db)
    except InternalMarksServiceError as exc:
        _raise_ims(exc)

    return InternalMarksResponse.model_validate(ims)


@router.post("/internal-marks/{ims_id}/submit", response_model=InternalMarksResponse)
async def submit_internal_marks(
    ims_id: UUID,
    current_user: CurrentUser = Depends(_faculty_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    GATE 1: Faculty submits internal marks for Dean review.
    Transitions PENDING → FACULTY_SUBMITTED. Computes and stores total_internal.
    """
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        ims = await InternalMarksService.submit(
            ims_id, faculty_user_id=current_user.user_id, db=db
        )
    except InternalMarksServiceError as exc:
        _raise_ims(exc)

    await AuditService.log(
        AuditEventType.INTERNAL_MARKS_SUBMITTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="internal_marks_summary",
        target_id=str(ims_id),
        metadata={
            "course_id": str(ims.course_id),
            "student_id": str(ims.student_id),
            "total_internal": float(ims.total_internal) if ims.total_internal else None,
        },
    )
    return InternalMarksResponse.model_validate(ims)


@router.post("/internal-marks/{ims_id}/lock", response_model=InternalMarksResponse)
async def lock_internal_marks(
    ims_id: UUID,
    current_user: CurrentUser = Depends(_dean_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    GATE 2: Dean locks internal marks. FACULTY_SUBMITTED → DEAN_LOCKED.
    After locking no further updates are permitted.
    """
    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        ims = await InternalMarksService.lock(
            ims_id, dean_user_id=current_user.user_id, db=db
        )
    except InternalMarksServiceError as exc:
        _raise_ims(exc)

    await AuditService.log(
        AuditEventType.INTERNAL_MARKS_LOCKED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="internal_marks_summary",
        target_id=str(ims_id),
        metadata={"course_id": str(ims.course_id), "student_id": str(ims.student_id)},
    )
    return InternalMarksResponse.model_validate(ims)


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
# Export — PDF question paper (STEP-14)
# ---------------------------------------------------------------------------

# Statuses where questions are readable (SEALED is excluded — service blocks it)
_PDF_ALLOWED_STATUSES = {
    "GENERATED", "SUBMITTED", "BOARD_APPROVED", "BOARD_RETURNED", "RELEASED",
}


@router.get("/{paper_id}/export/pdf")
async def export_pdf(
    paper_id:  UUID,
    set_label: str = Query(default="A", description="Set A or B"),
    current_user: CurrentUser = Depends(_read_dep()),
    db_info=Depends(get_tenant_context_dep),
):
    """
    Export a print-ready exam paper as a PDF.
    Role gate: ADMIN / DEAN / FACULTY / BOARD.
    Status gate: GENERATED or later, except SEALED (questions are inaccessible while sealed).
    No model answers are included.
    """
    from io import BytesIO
    from fastapi.responses import StreamingResponse

    db: AsyncSession = db_info["db"]
    schema: str      = db_info["schema_name"]
    tenant_id: UUID  = db_info["tenant_id"]

    try:
        paper = await ExamService.get(paper_id, db=db)
    except ExamServiceError as exc:
        _raise(exc)

    if paper.status not in _PDF_ALLOWED_STATUSES:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "EXPORT_NOT_ALLOWED",
                "message": (
                    f"PDF export is not available for papers with status {paper.status!r}. "
                    "Paper must be GENERATED or later (SEALED papers are excluded)."
                ),
            },
        )

    questions = await ExamService.get_questions(
        paper_id, set_label=set_label, include_answers=False, db=db
    )

    # Optional: look up course for header display
    course = None
    try:
        from sqlalchemy import select
        from app.modules.m01_program_advisor.models import Course
        result = await db.execute(select(Course).where(Course.id == paper.course_id))
        course = result.scalar_one_or_none()
    except Exception:
        pass

    from app.modules.m08_exam_setter.pdf_exporter import generate_exam_pdf
    pdf_bytes = generate_exam_pdf(paper, questions, course=course, set_label=set_label)

    await AuditService.log(
        AuditEventType.EXAM_PAPER_EXPORT_PDF,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        schema_name=schema,
        target_entity="exam_paper",
        target_id=str(paper_id),
        metadata={"set_label": set_label, "page_count_approx": len(questions)},
    )

    filename = f"exam_{paper_id}_set{set_label}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as pub_db:
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
