"""
M07 Research Supervision — Router.

RBAC
----
  _GUIDE    = ADMIN + (FACULTY role OR active FACULTY grant, e.g. a DEAN with a
              FACULTY grant) + GUIDE   (supervise, review, ratify)
  _STUDENT  = STUDENT                   (submit, attend viva, view own)
  _READ     = ADMIN + DEAN + FACULTY + GUIDE

Endpoint summary (guide)
------------------------
  POST   /problems/propose                   generate AI problems for guide (returns JSON, not stored)
  POST   /problems/ai-store                  guide stores one AI-generated problem
  GET    /problems                           list problems for authenticated guide
  GET    /problems/{id}                      get problem detail
  POST   /problems/{id}/decide               guide decides on student proposal (HUMAN GATE 1)
  GET    /documents                          list documents for guide
  GET    /documents/{id}                     document detail + evaluation report
  POST   /documents/{id}/review              guide approve/revision (HUMAN GATE 2)
  GET    /vivas                              list viva sessions for guide
  POST   /vivas                              schedule a viva session
  GET    /vivas/{id}                         viva detail
  POST   /vivas/{id}/ratify                  ratify viva evaluation (HUMAN GATE 3)

Endpoint summary (student)
--------------------------
  POST   /student/problems                   submit research problem proposal
  GET    /student/problems                   list own proposals
  GET    /student/problems/{id}              proposal detail + AI advisory
  POST   /student/documents                  submit document (create record)
  PATCH  /student/documents/{id}/file        set file_url after upload
  GET    /student/documents/{id}             document detail
  GET    /student/vivas                      list own viva sessions
  GET    /student/vivas/{id}                 viva detail (hides guide evaluation until ratified)
  POST   /student/vivas/{token}/consent      record consent
  POST   /student/vivas/{token}/respond      submit one response
  POST   /student/vivas/{token}/complete     mark complete + provide video URL

Common
------
  GET    /jobs/{job_id}                      poll job status
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.dependencies import get_tenant_db_dep, require_roles, require_responsibility
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.rate_limiting import limiter
from app.modules.m07_research_supervision.schemas import (
    AIGeneratedProblemCreate,
    DocumentFileUpdate,
    DocumentListResponse,
    DocumentResponse,
    DocumentSubmit,
    GeneratedProblemsResponse,
    GuideDecisionRequest,
    GuideDocumentReviewRequest,
    GuideUserResponse,
    JobStatusResponse,
    ProblemCreate,
    ProblemListResponse,
    ProblemResponse,
    VivaCompleteRequest,
    VivaConductRequest,
    VivaConsentRequest,
    VivaListResponse,
    VivaRatifyRequest,
    VivaResponseSubmit,
    VivaScheduleRequest,
    VivaSessionResponse,
)
from app.modules.m07_research_supervision.service import (
    DocumentService,
    ProblemService,
    ResearchServiceError,
    VivaService,
)

router = APIRouter(tags=["research-supervision"])

_GUIDE    = require_responsibility(TenantRole.ADMIN, TenantRole.FACULTY, TenantRole.GUIDE)
_STUDENT  = require_roles(TenantRole.STUDENT)
_READ     = require_roles(TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY, TenantRole.GUIDE)
_ALL      = require_roles(
    TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY,
    TenantRole.GUIDE, TenantRole.STUDENT, TenantRole.BOARD,
)


def _svc_error(exc: ResearchServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "message": exc.message},
    )


# ===========================================================================
# Guide — Problem management
# ===========================================================================

@router.post("/problems/propose", response_model=GeneratedProblemsResponse)
@limiter.limit("10/minute")
async def generate_ai_problems(
    request: Request,
    payload: AIGeneratedProblemCreate,
    current_user: CurrentUser = Depends(_GUIDE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Generate AI-suggested research problems for a guide's area (not stored)."""
    result = await ProblemService.create_ai_generated(
        guide_user_id=current_user.user_id,
        research_area=payload.research_area,
        num_problems=payload.num_problems,
    )
    await AuditService.log(
        AuditEventType.RESEARCH_PROBLEM_AI_GENERATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="research_problem",
        target_id=None,
        metadata={"area": payload.research_area, "count": payload.num_problems},
    )
    from app.modules.m07_research_supervision.schemas import GeneratedProblemItem
    return GeneratedProblemsResponse(
        problems=[
            GeneratedProblemItem(
                title=p.title,
                abstract=p.abstract,
                research_questions=p.research_questions,
                reasoning=p.reasoning,
            )
            for p in result.problems
        ],
        ai_model=result.ai_model,
    )


@router.post("/problems/ai-store", response_model=ProblemResponse, status_code=201)
async def store_ai_generated_problem(
    payload: dict,
    current_user: CurrentUser = Depends(_GUIDE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Guide stores one AI-generated problem to offer to students."""
    try:
        problem = await ProblemService.store_ai_generated_problem(
            guide_user_id=current_user.user_id,
            title=payload.get("title", ""),
            abstract=payload.get("abstract", ""),
            research_questions=payload.get("research_questions", []),
            db=db,
        )
    except ResearchServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.RESEARCH_PROBLEM_AI_GENERATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="research_problem",
        target_id=str(problem.id),
        metadata={"source": "AI_GENERATED", "title": problem.title},
    )
    return ProblemResponse.model_validate(problem)


@router.get("/problems", response_model=ProblemListResponse)
async def list_guide_problems(
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    items, total = await ProblemService.list_for_guide(
        guide_user_id=current_user.user_id,
        status=status, offset=offset, limit=limit, db=db,
    )
    return ProblemListResponse(
        items=[ProblemResponse.model_validate(p) for p in items],
        total=total, offset=offset, limit=limit,
    )


@router.get("/problems/{problem_id}", response_model=ProblemResponse)
async def get_problem(
    problem_id: UUID,
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        problem = await ProblemService.get(problem_id, db=db)
    except ResearchServiceError as exc:
        raise _svc_error(exc)
    return ProblemResponse.model_validate(problem)


@router.post("/problems/{problem_id}/decide", response_model=ProblemResponse)
async def guide_decide_problem(
    problem_id: UUID,
    payload: GuideDecisionRequest,
    current_user: CurrentUser = Depends(_GUIDE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """HUMAN GATE 1 — Guide explicitly decides on research problem proposal."""
    try:
        problem = await ProblemService.guide_decide(
            problem_id, payload,
            guide_user_id=current_user.user_id,
            db=db,
        )
    except ResearchServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.RESEARCH_PROBLEM_GUIDE_DECIDED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="research_problem",
        target_id=str(problem_id),
        metadata={"decision": payload.decision, "note": payload.guide_note},
    )
    return ProblemResponse.model_validate(problem)


# ===========================================================================
# Guide — Document review
# ===========================================================================

@router.get("/documents", response_model=DocumentListResponse)
async def list_guide_documents(
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    items, total = await DocumentService.list_for_guide(
        guide_user_id=current_user.user_id,
        status=status, offset=offset, limit=limit, db=db,
    )
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in items],
        total=total, offset=offset, limit=limit,
    )


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: UUID,
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        doc = await DocumentService.get(doc_id, db=db)
    except ResearchServiceError as exc:
        raise _svc_error(exc)
    return DocumentResponse.model_validate(doc)


@router.get("/documents/{doc_id}/download-url")
async def get_document_download_url(
    doc_id: UUID,
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Return a short-lived presigned GET URL for the document's uploaded file.

    Bypasses the storage-service owner check because the guide is authorised
    to view any document assigned to them via the research problem.
    """
    from fastapi import HTTPException
    try:
        doc = await DocumentService.get(doc_id, db=db)
    except ResearchServiceError as exc:
        raise _svc_error(exc)

    if not doc.file_url:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_FILE", "message": "No file has been uploaded for this document."},
        )

    from app.core.storage.repository import StorageRepository
    from app.config import settings

    expires_in_sec = settings.PRESIGNED_URL_EXPIRY_MINUTES_GET * 60
    try:
        presigned_url = await StorageRepository.generate_presigned_get_url(
            object_key=doc.file_url,
            expires_in_seconds=expires_in_sec,
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail={"error": "STORAGE_ERROR", "message": "Could not generate download URL."},
        )

    return {"presigned_url": presigned_url, "expires_in_seconds": expires_in_sec}


@router.post("/documents/{doc_id}/review", response_model=DocumentResponse)
async def guide_review_document(
    doc_id: UUID,
    payload: GuideDocumentReviewRequest,
    current_user: CurrentUser = Depends(_GUIDE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """HUMAN GATE 2 — Guide reviews document evaluation."""
    try:
        doc = await DocumentService.guide_review(
            doc_id, payload,
            guide_user_id=current_user.user_id,
            db=db,
        )
    except ResearchServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.RESEARCH_DOCUMENT_GUIDE_REVIEWED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="research_document",
        target_id=str(doc_id),
        metadata={"decision": payload.decision},
    )
    return DocumentResponse.model_validate(doc)


# ===========================================================================
# Guide — Viva sessions
# ===========================================================================

@router.post("/vivas", response_model=VivaSessionResponse, status_code=201)
async def schedule_viva(
    payload: VivaScheduleRequest,
    current_user: CurrentUser = Depends(_GUIDE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        viva = await VivaService.schedule(
            payload, guide_user_id=current_user.user_id, db=db
        )
    except ResearchServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.VIVA_SESSION_SCHEDULED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="viva_session",
        target_id=str(viva.id),
        metadata={
            "problem_id":  str(payload.research_problem_id),
            "document_id": str(payload.document_id),
            "student_id":  str(viva.student_user_id),
        },
    )
    return VivaSessionResponse.model_validate(viva)


@router.get("/vivas", response_model=VivaListResponse)
async def list_guide_vivas(
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    items, total = await VivaService.list_for_guide(
        guide_user_id=current_user.user_id,
        status=status, offset=offset, limit=limit, db=db,
    )
    return VivaListResponse(
        items=[VivaSessionResponse.model_validate(v) for v in items],
        total=total, offset=offset, limit=limit,
    )


@router.get("/vivas/{viva_id}", response_model=VivaSessionResponse)
async def get_viva(
    viva_id: UUID,
    current_user: CurrentUser = Depends(_READ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        viva = await VivaService.get(viva_id, db=db)
    except ResearchServiceError as exc:
        raise _svc_error(exc)
    return VivaSessionResponse.model_validate(viva)


@router.post("/vivas/{viva_id}/ratify", response_model=VivaSessionResponse)
async def ratify_viva(
    viva_id: UUID,
    payload: VivaRatifyRequest,
    current_user: CurrentUser = Depends(_GUIDE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """HUMAN GATE 3 — Guide ratifies viva evaluation."""
    try:
        viva = await VivaService.ratify(
            viva_id, payload,
            guide_user_id=current_user.user_id,
            db=db,
        )
    except ResearchServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.VIVA_GUIDE_RATIFIED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="viva_session",
        target_id=str(viva_id),
        metadata={
            "overall_guide_score": float(viva.overall_guide_score or 0),
            "has_note": bool(payload.ratification_note),
        },
    )
    return VivaSessionResponse.model_validate(viva)


@router.post("/vivas/{viva_id}/conduct", response_model=VivaSessionResponse)
async def conduct_viva(
    viva_id: UUID,
    payload: VivaConductRequest,
    current_user: CurrentUser = Depends(_GUIDE),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Guide conducts an offline viva: submits all Q&A responses and triggers AI evaluation."""
    try:
        viva, job_id = await VivaService.conduct(
            viva_id, payload,
            guide_user_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ResearchServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.VIVA_SESSION_STARTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="viva_session",
        target_id=str(viva_id),
        metadata={
            "mode":       "offline_guide_conducted",
            "responses":  len(payload.responses),
            "eval_job_id": str(job_id),
        },
    )
    return VivaSessionResponse.model_validate(viva)


# ===========================================================================
# Guide directory — accessible to all authenticated tenant users
# ===========================================================================

@router.get("/guides", response_model=list[GuideUserResponse])
async def list_active_guides(
    current_user: CurrentUser = Depends(_ALL),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Return active GUIDE users in this tenant for research proposal guide selection."""
    from app.core.auth.repository import TenantRepository
    guides = await TenantRepository.list_active_guides(db)
    return [GuideUserResponse.model_validate(g) for g in guides]


# ===========================================================================
# Student — Problem proposals
# ===========================================================================

@router.post("/student/problems", response_model=ProblemResponse, status_code=201)
async def student_submit_proposal(
    payload: ProblemCreate,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        problem, job_id = await ProblemService.create_student_proposal(
            payload,
            student_user_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ResearchServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.RESEARCH_PROBLEM_SUBMITTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="research_problem",
        target_id=str(problem.id),
        metadata={"title": problem.title, "eval_job_id": str(job_id)},
    )
    return ProblemResponse.model_validate(problem)


@router.get("/student/problems", response_model=ProblemListResponse)
async def student_list_proposals(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    items, total = await ProblemService.list_for_student(
        current_user.user_id, offset=offset, limit=limit, db=db
    )
    return ProblemListResponse(
        items=[ProblemResponse.model_validate(p) for p in items],
        total=total, offset=offset, limit=limit,
    )


@router.get("/student/problems/{problem_id}", response_model=ProblemResponse)
async def student_get_proposal(
    problem_id: UUID,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        problem = await ProblemService.get(problem_id, db=db)
    except ResearchServiceError as exc:
        raise _svc_error(exc)
    if problem.student_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": "Access denied."})
    return ProblemResponse.model_validate(problem)


@router.get("/student/problems/{problem_id}/documents", response_model=DocumentListResponse)
async def student_list_problem_documents(
    problem_id: UUID,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """List all documents the student has submitted for one of their proposals."""
    try:
        problem = await ProblemService.get(problem_id, db=db)
    except ResearchServiceError as exc:
        raise _svc_error(exc)
    if problem.student_user_id != current_user.user_id:
        raise HTTPException(
            status_code=403,
            detail={"error": "FORBIDDEN", "message": "Access denied."},
        )
    items = await DocumentService.list_for_problem(problem_id, db=db)
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in items],
        total=len(items),
        offset=0,
        limit=len(items),
    )


# ===========================================================================
# Student — Document submission
# ===========================================================================

@router.post("/student/documents", response_model=DocumentResponse, status_code=201)
async def student_submit_document(
    payload: DocumentSubmit,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        doc, job_id = await DocumentService.submit(
            payload,
            student_user_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ResearchServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.RESEARCH_DOCUMENT_SUBMITTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="research_document",
        target_id=str(doc.id),
        metadata={"problem_id": str(payload.research_problem_id), "version": doc.version},
    )
    return DocumentResponse.model_validate(doc)


@router.patch("/student/documents/{doc_id}/file", response_model=DocumentResponse)
async def student_set_file_url(
    doc_id: UUID,
    payload: DocumentFileUpdate,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        doc = await DocumentService.update_file_url(
            doc_id,
            file_url=payload.file_url,
            file_name=payload.file_name,
            student_user_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ResearchServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.RESEARCH_DOCUMENT_EVAL_QUEUED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="research_document",
        target_id=str(doc_id),
        metadata={"file_name": payload.file_name},
    )
    return DocumentResponse.model_validate(doc)


@router.get("/student/documents/{doc_id}", response_model=DocumentResponse)
async def student_get_document(
    doc_id: UUID,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        doc = await DocumentService.get(doc_id, db=db)
    except ResearchServiceError as exc:
        raise _svc_error(exc)
    if doc.student_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": "Access denied."})
    return DocumentResponse.model_validate(doc)


# ===========================================================================
# Student — Viva session
# ===========================================================================

@router.get("/student/vivas", response_model=VivaListResponse)
async def student_list_vivas(
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    items = await VivaService.list_for_student(current_user.user_id, db=db)
    return VivaListResponse(
        items=[VivaSessionResponse.model_validate(v) for v in items],
        total=len(items), offset=0, limit=len(items),
    )


@router.get("/student/vivas/{viva_id}", response_model=VivaSessionResponse)
async def student_get_viva(
    viva_id: UUID,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        viva = await VivaService.get(viva_id, db=db)
    except ResearchServiceError as exc:
        raise _svc_error(exc)
    if viva.student_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": "Access denied."})
    # Hide guide evaluation until ratified
    if viva.status != "GUIDE_RATIFIED":
        viva = _mask_guide_eval(viva)
    return VivaSessionResponse.model_validate(viva)


def _mask_guide_eval(viva):
    """Prevent student from seeing guide evaluation before ratification."""
    viva.guide_evaluation    = None
    viva.overall_guide_score = None
    return viva


@router.post("/student/vivas/{session_token}/consent")
async def student_record_consent(
    session_token: str,
    payload: VivaConsentRequest,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Student records explicit consent before recording begins. DPDP compliance."""
    try:
        viva = await VivaService.get_by_token(session_token, db=db)
    except ResearchServiceError as exc:
        raise _svc_error(exc)
    if viva.student_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": "Access denied."})
    await VivaService.record_consent(viva.id, db=db)

    await AuditService.log(
        AuditEventType.VIVA_SESSION_STARTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="viva_session",
        target_id=str(viva.id),
        metadata={"consent": True},
    )
    return {"status": "consent_recorded", "viva_id": str(viva.id)}


@router.post("/student/vivas/{session_token}/respond")
async def student_submit_response(
    session_token: str,
    payload: VivaResponseSubmit,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """Student submits one answer; returns follow-up question if generated."""
    try:
        viva = await VivaService.get_by_token(session_token, db=db)
    except ResearchServiceError as exc:
        raise _svc_error(exc)
    if viva.student_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": "Access denied."})

    try:
        followup = await VivaService.submit_response(
            viva.id,
            question_id=payload.question_id,
            response_text=payload.response_text,
            start_ms=payload.start_ms,
            end_ms=payload.end_ms,
            db=db,
        )
    except ResearchServiceError as exc:
        raise _svc_error(exc)

    return {"status": "response_recorded", "followup_question": followup}


@router.post("/student/vivas/{session_token}/complete")
async def student_complete_viva(
    session_token: str,
    payload: VivaCompleteRequest,
    current_user: CurrentUser = Depends(_STUDENT),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        viva = await VivaService.get_by_token(session_token, db=db)
    except ResearchServiceError as exc:
        raise _svc_error(exc)
    if viva.student_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": "Access denied."})

    try:
        updated_viva, job_id = await VivaService.complete(
            viva.id,
            video_url=payload.video_url,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ResearchServiceError as exc:
        raise _svc_error(exc)

    await AuditService.log(
        AuditEventType.VIVA_SESSION_COMPLETED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="viva_session",
        target_id=str(viva.id),
        metadata={"eval_job_id": str(job_id)},
    )
    return {"status": "session_completed", "viva_id": str(viva.id), "eval_job_id": str(job_id)}


# ===========================================================================
# Job status poll
# ===========================================================================

@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: UUID,
    current_user: CurrentUser = Depends(
        require_roles(TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY,
                      TenantRole.GUIDE, TenantRole.STUDENT)
    ),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    from app.database import AsyncSessionLocal
    from app.modules.m07_research_supervision.repository import TaskJobPublicRepository

    async with AsyncSessionLocal() as pub_db:
        job = await TaskJobPublicRepository.get_by_id(
            job_id, current_user.tenant_id, db=pub_db
        )

    if job is None:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Job not found."})

    return JobStatusResponse(
        job_id=job["id"],
        status=job["status"],
        result=job["result"],
        error=job["error"],
        created_at=job["created_at"],
        completed_at=job["completed_at"],
    )
