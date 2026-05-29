"""
M05 Learning Material Packager — router (STEP-12).

RBAC
----
  _WRITE  = ADMIN + FACULTY  (curation trigger, RAG index, item mutations)
  _READ   = ADMIN + DEAN + FACULTY  (package list/get, job status)
  _FULL   = ADMIN + DEAN + FACULTY + STUDENT  (package/item reads, Q&A)

Router is pure HTTP glue.  All business logic lives in LearningPackageService.

Endpoint summary
----------------
  POST   /curate                              trigger curation
  POST   /{package_id}/index                 trigger RAG indexing
  GET    /jobs/{job_id}                       poll job status
  GET    /                                    list packages (syllabus_id required)
  GET    /{package_id}                        get full package detail
  GET    /{package_id}/status                 lightweight status poll
  GET    /{package_id}/items                  list package items
  POST   /{package_id}/items                  add faculty item
  DELETE /{package_id}/items/{item_id}        remove item
  PATCH  /{package_id}/items/{item_id}/recommend  toggle faculty recommendation
  POST   /{package_id}/ask                    submit Q&A question
  GET    /{package_id}/qa/sessions            list student Q&A sessions
  GET    /{package_id}/qa/sessions/{session_id}  get session with messages
"""
from __future__ import annotations

from uuid import UUID

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.rate_limiting import limiter
from app.modules.m05_learning_materials.models import PackageStatus
from app.modules.m05_learning_materials.schemas import (
    CurationJobResponse,
    CurationTriggerRequest,
    FacultyAddItemRequest,
    FacultyRecommendToggle,
    LearningPackageListResponse,
    LearningPackageResponse,
    PackageItemResponse,
    PackageQASessionResponse,
    PackageQASessionWithMessages,
    PackageStatusResponse,
    RAGAnswerResponse,
    StudentQuestionRequest,
)
from app.modules.m05_learning_materials.service import (
    LearningPackageService,
    PackageServiceError,
)

router = APIRouter(tags=["learning-packages"])
logger = logging.getLogger("vidya.m05.router")

# ---------------------------------------------------------------------------
# RBAC role sets
# ---------------------------------------------------------------------------
_WRITE = (TenantRole.ADMIN, TenantRole.FACULTY)
_READ  = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)
_FULL  = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY, TenantRole.STUDENT)


def _err(e: PackageServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


def _404(entity: str = "Learning package") -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": "NOT_FOUND", "message": f"{entity} not found."},
    )


# ===========================================================================
# Curation trigger
# ===========================================================================

@router.post("/curate", response_model=CurationJobResponse, status_code=202)
@limiter.limit("5/minute")
async def trigger_curation(
    request: Request,
    payload: CurationTriggerRequest,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CurationJobResponse:
    try:
        result = await LearningPackageService.dispatch_curation(
            syllabus_id=payload.syllabus_id,
            unit_number=payload.unit_number,
            created_by=current_user.user_id,
            tenant_id=current_user.tenant_id,
            tenant_schema=current_user.schema_name,
            top_n=payload.top_n,
            db=db,
        )
    except PackageServiceError as e:
        raise _err(e)
    return result


# ===========================================================================
# RAG indexing trigger
# ===========================================================================

@router.post("/{package_id}/index", status_code=202)
@limiter.limit("5/minute")
async def trigger_rag_indexing(
    request: Request,
    package_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        job_id = await LearningPackageService.dispatch_rag_indexing(
            package_id=package_id,
            tenant_id=current_user.tenant_id,
            tenant_schema=current_user.schema_name,
            db=db,
        )
    except PackageServiceError as e:
        raise _err(e)
    return {"job_id": job_id, "status": "queued"}


# ===========================================================================
# Job status — fixed path must precede /{package_id}
# ===========================================================================

@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    job = await LearningPackageService.get_job_status(
        job_id=job_id, tenant_id=current_user.tenant_id, db=db
    )
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "message": "Job not found."},
        )
    return job


# ===========================================================================
# Package list / get
# ===========================================================================

@router.get("", response_model=LearningPackageListResponse)
async def list_packages(
    syllabus_id: UUID | None = Query(None, description="Filter by syllabus; omit to list all"),
    status: PackageStatus | None = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> LearningPackageListResponse:
    total, pkgs = await LearningPackageService.list_packages(
        syllabus_id=syllabus_id,
        status_filter=status,
        page=page,
        page_size=page_size,
        db=db,
    )
    return LearningPackageListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[LearningPackageResponse.model_validate(p) for p in pkgs],
    )


@router.get("/{package_id}", response_model=LearningPackageResponse)
async def get_package(
    package_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_FULL)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> LearningPackageResponse:
    pkg = await LearningPackageService.get_package(package_id, db=db)
    if pkg is None:
        raise _404()
    return LearningPackageResponse.model_validate(pkg)


@router.get("/{package_id}/status", response_model=PackageStatusResponse)
async def get_package_status(
    package_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_FULL)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> PackageStatusResponse:
    pkg = await LearningPackageService.get_package(package_id, db=db)
    if pkg is None:
        raise _404()
    return PackageStatusResponse.model_validate(pkg)


# ===========================================================================
# Package items
# ===========================================================================

@router.get("/{package_id}/items", response_model=list[PackageItemResponse])
async def list_items(
    package_id: UUID,
    faculty_only: bool = Query(False, description="Return only faculty-recommended items"),
    current_user: CurrentUser = Depends(require_roles(*_FULL)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[PackageItemResponse]:
    items = await LearningPackageService.list_items(
        package_id, faculty_only=faculty_only, db=db
    )
    return [PackageItemResponse.model_validate(i) for i in items]


@router.post("/{package_id}/items", response_model=PackageItemResponse, status_code=201)
async def add_faculty_item(
    package_id: UUID,
    payload: FacultyAddItemRequest,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> PackageItemResponse:
    try:
        item = await LearningPackageService.add_faculty_item(
            package_id=package_id,
            payload=payload,
            added_by=current_user.user_id,
            db=db,
        )
    except PackageServiceError as e:
        raise _err(e)

    await AuditService.log(
        AuditEventType.LEARNING_PACKAGE_ITEM_ADDED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="PackageItem",
        target_id=str(item.id),
        metadata={
            "package_id":  str(package_id),
            "source_type": payload.source_type.value,
            "title":       payload.title,
        },
    )
    return PackageItemResponse.model_validate(item)


@router.delete("/{package_id}/items/{item_id}", status_code=200)
async def remove_item(
    package_id: UUID,
    item_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await LearningPackageService.remove_item(
            package_id=package_id, item_id=item_id, db=db
        )
    except PackageServiceError as e:
        raise _err(e)

    await AuditService.log(
        AuditEventType.LEARNING_PACKAGE_ITEM_REMOVED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="PackageItem",
        target_id=str(item_id),
        metadata={"package_id": str(package_id)},
    )
    return {"status": "removed"}


# ===========================================================================
# Faculty note upload (PDF / TXT / DOCX)
# ===========================================================================

@router.post("/{package_id}/notes", response_model=PackageItemResponse, status_code=201)
@limiter.limit("10/minute")
async def upload_faculty_note(
    request: Request,
    package_id: UUID,
    file: UploadFile = File(..., description="PDF, plain-text, or DOCX file (max 20 MB)"),
    title: str | None = Form(default=None, description="Override display title (defaults to filename)"),
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> PackageItemResponse:
    """Upload a faculty note file and add it as a FACULTY_NOTE item.

    The server extracts text from PDF / TXT / DOCX and stores the result in the
    package item's metadata so it can be indexed by the RAG pipeline.
    The raw file is also stored in S3/MinIO (best-effort; not required for Q&A).

    RBAC: ADMIN, FACULTY only.
    """
    file_bytes = await file.read()
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "note"

    try:
        item = await LearningPackageService.ingest_faculty_note(
            package_id=package_id,
            file_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
            title=title,
            added_by=current_user.user_id,
            tenant_slug=current_user.schema_name.replace("tenant_", "", 1),
            db=db,
        )
    except PackageServiceError as e:
        raise _err(e)

    await AuditService.log(
        AuditEventType.LEARNING_PACKAGE_FACULTY_NOTE_UPLOADED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="PackageItem",
        target_id=str(item.id),
        metadata={
            "package_id":  str(package_id),
            "filename":    filename,
            "word_count":  (item.metadata_ or {}).get("word_count", 0),
            "has_storage": bool((item.metadata_ or {}).get("storage_key")),
        },
    )
    return PackageItemResponse.model_validate(item)


@router.patch(
    "/{package_id}/items/{item_id}/recommend",
    response_model=PackageItemResponse,
)
async def toggle_recommendation(
    package_id: UUID,
    item_id: UUID,
    payload: FacultyRecommendToggle,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> PackageItemResponse:
    try:
        item = await LearningPackageService.toggle_faculty_recommendation(
            package_id=package_id,
            item_id=item_id,
            value=payload.faculty_recommended,
            db=db,
        )
    except PackageServiceError as e:
        raise _err(e)

    await AuditService.log(
        AuditEventType.LEARNING_PACKAGE_ITEM_RECOMMENDATION_TOGGLED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="PackageItem",
        target_id=str(item_id),
        metadata={
            "package_id":        str(package_id),
            "faculty_recommended": payload.faculty_recommended,
        },
    )
    return PackageItemResponse.model_validate(item)


# ===========================================================================
# Q&A
# ===========================================================================

@router.post("/{package_id}/ask", response_model=RAGAnswerResponse)
async def ask_question(
    package_id: UUID,
    payload: StudentQuestionRequest,
    session_id: UUID | None = Query(None, description="Continue an existing Q&A session"),
    current_user: CurrentUser = Depends(require_roles(*_FULL)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> RAGAnswerResponse:
    try:
        result = await LearningPackageService.ask_question(
            package_id=package_id,
            student_user_id=current_user.user_id,
            question=payload.question,
            tenant_schema=current_user.schema_name,
            session_id=session_id,
            db=db,
        )
    except PackageServiceError as e:
        logger.warning(
            "m05.router: ask failed (package=%s session=%s code=%s question=%r): %s",
            package_id, session_id, e.code, payload.question[:60], e.message,
        )
        raise _err(e)
    return RAGAnswerResponse(**result)


@router.get(
    "/{package_id}/qa/sessions",
    response_model=list[PackageQASessionResponse],
)
async def list_qa_sessions(
    package_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_FULL)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[PackageQASessionResponse]:
    sessions = await LearningPackageService.list_qa_sessions(
        package_id=package_id,
        student_user_id=current_user.user_id,
        db=db,
    )
    return [PackageQASessionResponse.model_validate(s) for s in sessions]


@router.get(
    "/{package_id}/qa/sessions/{session_id}",
    response_model=PackageQASessionWithMessages,
)
async def get_qa_session(
    package_id: UUID,
    session_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_FULL)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> PackageQASessionWithMessages:
    session = await LearningPackageService.get_qa_session(session_id, db=db)
    if session is None:
        raise _404("Q&A session")
    return PackageQASessionWithMessages.model_validate(session)
