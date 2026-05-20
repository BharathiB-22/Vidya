"""
M03 Course Kit router — 26 endpoints, RBAC enforced.

RBAC
----
  _WRITE  = ADMIN + FACULTY  (generate, publish, archive, fork, edit children)
  _READ   = ADMIN + DEAN + FACULTY  (any view)
  _EXPORT = ADMIN + DEAN + FACULTY  (reserved for STEP-11 export endpoints)

Sensitive field gating (DEAN role never sees):
  - KitSlide.speaker_notes → None
  - KitQuizlet.answer_key  → None
  - KitAssignment.model_answer → None

All business logic lives in CourseKitService.
Router is pure HTTP glue: deserialise → call service → audit → serialise.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.rate_limiting import limiter
from app.modules.m03_course_kit.models import CourseKitStatus
from app.modules.m03_course_kit.schemas import (
    ArchiveRequest,
    ComplianceCheckResponse,
    CourseKitCreate,
    CourseKitDetail,
    CourseKitListResponse,
    CourseKitResponse,
    CourseKitStatusResponse,
    CourseKitUpdate,
    CourseKitVersionResponse,
    ForkRequest,
    GenerateKitRequest,
    KitAIJobResponse,
    KitAssignmentCreate,
    KitExportJobResponse,
    KitExportRequest,
    KitAssignmentResponse,
    KitAssignmentUpdate,
    KitQuizletCreate,
    KitQuizletResponse,
    KitQuizletUpdate,
    KitSlideCreate,
    KitSlideReorder,
    KitSlideResponse,
    KitSlideUpdate,
    PublishRequest,
)
from app.modules.m03_course_kit.service import CourseKitService, KitServiceError

router = APIRouter(tags=["course-kits"])

# ---------------------------------------------------------------------------
# RBAC role sets
# ---------------------------------------------------------------------------
_WRITE  = (TenantRole.ADMIN, TenantRole.FACULTY)
_READ   = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)


def _err(e: KitServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


def _404(entity: str = "Course kit") -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": "NOT_FOUND", "message": f"{entity} not found."},
    )


# ---------------------------------------------------------------------------
# Sensitive-field gating for DEAN role
# ---------------------------------------------------------------------------

def _gate_slide(slide: KitSlideResponse, role: str) -> KitSlideResponse:
    if role == TenantRole.DEAN.value:
        return slide.model_copy(update={"speaker_notes": None})
    return slide


def _gate_quizlet(quizlet: KitQuizletResponse, role: str) -> KitQuizletResponse:
    if role == TenantRole.DEAN.value:
        return quizlet.model_copy(update={"answer_key": None})
    return quizlet


def _gate_assignment(
    assignment: KitAssignmentResponse, role: str
) -> KitAssignmentResponse:
    if role == TenantRole.DEAN.value:
        return assignment.model_copy(update={"model_answer": None})
    return assignment


def _gate_detail(detail: CourseKitDetail, role: str) -> CourseKitDetail:
    """Null sensitive fields in a full CourseKitDetail for DEAN."""
    if role != TenantRole.DEAN.value:
        return detail
    return detail.model_copy(update={
        "slides":      [_gate_slide(s, role) for s in detail.slides],
        "quizlets":    [_gate_quizlet(q, role) for q in detail.quizlets],
        "assignments": [_gate_assignment(a, role) for a in detail.assignments],
    })


# ===========================================================================
# Kit CRUD
# ===========================================================================

@router.post("", response_model=CourseKitResponse, status_code=201)
async def create_kit(
    payload: CourseKitCreate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitResponse:
    try:
        kit = await CourseKitService.create_kit(
            payload, created_by=current_user.user_id, db=db
        )
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_CREATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="CourseKit",
        target_id=str(kit.id),
        metadata={
            "syllabus_id": str(kit.syllabus_id),
            "unit_number": kit.unit_number,
            "version":     kit.version,
        },
    )
    return CourseKitResponse.model_validate(kit)


@router.get("", response_model=CourseKitListResponse)
async def list_kits(
    syllabus_id: UUID = Query(..., description="Syllabus ID (required)"),
    status: CourseKitStatus | None = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitListResponse:
    total, items = await CourseKitService.list_kits(
        syllabus_id=syllabus_id,
        status_filter=status,
        page=page,
        page_size=page_size,
        db=db,
    )
    return CourseKitListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[CourseKitResponse.model_validate(k) for k in items],
    )


@router.get("/{kit_id}", response_model=CourseKitDetail)
async def get_kit(
    kit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitDetail:
    kit = await CourseKitService.get_kit_detail(kit_id, db=db)
    if kit is None:
        raise _404()
    detail = CourseKitDetail.model_validate(kit)
    return _gate_detail(detail, current_user.role)


@router.get("/{kit_id}/status", response_model=CourseKitStatusResponse)
async def get_kit_status(
    kit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitStatusResponse:
    kit = await CourseKitService.get_kit(kit_id, db=db)
    if kit is None:
        raise _404()
    return CourseKitStatusResponse.model_validate(kit)


@router.patch("/{kit_id}", response_model=CourseKitResponse)
async def update_kit(
    kit_id: UUID,
    payload: CourseKitUpdate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitResponse:
    try:
        kit = await CourseKitService.update_kit(kit_id, payload, db=db)
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="CourseKit",
        target_id=str(kit_id),
        metadata={"changes": payload.model_dump(exclude_none=True)},
    )
    return CourseKitResponse.model_validate(kit)


@router.delete("/{kit_id}", status_code=200)
async def delete_kit(
    kit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await CourseKitService.delete_kit(kit_id, db=db)
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_DELETED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="CourseKit",
        target_id=str(kit_id),
        metadata={"kit_id": str(kit_id)},
    )
    return {"status": "deleted"}


@router.get("/{kit_id}/versions", response_model=list[CourseKitVersionResponse])
async def list_versions(
    kit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[CourseKitVersionResponse]:
    kit = await CourseKitService.get_kit(kit_id, db=db)
    if kit is None:
        raise _404()
    versions = await CourseKitService.list_versions(
        kit.syllabus_id, kit.unit_number, db=db
    )
    return [CourseKitVersionResponse.model_validate(v) for v in versions]


# ===========================================================================
# AI generation
# ===========================================================================

@router.post("/{kit_id}/generate", response_model=KitAIJobResponse)
@limiter.limit("5/minute")
async def generate_kit(
    request: Request,
    kit_id: UUID,
    payload: GenerateKitRequest,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> KitAIJobResponse:
    # If caller provides updated generation parameters, persist them first.
    if any([
        payload.custom_instructions is not None,
        payload.complexity_level is not None,
        payload.tone is not None,
    ]):
        try:
            await CourseKitService.update_kit(
                kit_id,
                CourseKitUpdate(
                    custom_instructions=payload.custom_instructions,
                    complexity_level=payload.complexity_level,
                    tone=payload.tone,
                ),
                db=db,
            )
        except KitServiceError as e:
            raise _err(e)

    try:
        job_id = await CourseKitService.dispatch_kit_generation(
            kit_id=kit_id,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except KitServiceError as e:
        raise _err(e)

    await AuditService.log(
        AuditEventType.COURSE_KIT_GENERATION_QUEUED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="CourseKit",
        target_id=str(kit_id),
        metadata={"job_id": job_id},
    )
    return KitAIJobResponse(job_id=UUID(job_id), kit_id=kit_id)


@router.get("/{kit_id}/jobs/{job_id}")
async def get_generation_job(
    kit_id: UUID,
    job_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    job = await CourseKitService.get_job_status(
        job_id=job_id, tenant_id=current_user.tenant_id, db=db
    )
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "message": "Job not found."},
        )
    return job


# ===========================================================================
# State transitions
# ===========================================================================

@router.post("/{kit_id}/publish", response_model=CourseKitStatusResponse)
async def publish_kit(
    kit_id: UUID,
    payload: PublishRequest,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitStatusResponse:
    try:
        kit = await CourseKitService.publish_kit(
            kit_id, published_by=current_user.user_id, db=db
        )
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_PUBLISHED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="CourseKit",
        target_id=str(kit_id),
        metadata={"version": kit.version, "comment": payload.comment},
    )
    return CourseKitStatusResponse.model_validate(kit)


@router.post("/{kit_id}/archive", response_model=CourseKitStatusResponse)
async def archive_kit(
    kit_id: UUID,
    payload: ArchiveRequest,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitStatusResponse:
    try:
        kit = await CourseKitService.archive_kit(kit_id, db=db)
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_ARCHIVED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="CourseKit",
        target_id=str(kit_id),
        metadata={"reason": payload.reason},
    )
    return CourseKitStatusResponse.model_validate(kit)


@router.post("/{kit_id}/fork", response_model=CourseKitStatusResponse, status_code=201)
async def fork_kit(
    kit_id: UUID,
    payload: ForkRequest,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitStatusResponse:
    try:
        new_kit = await CourseKitService.fork_kit(
            kit_id,
            forked_by=current_user.user_id,
            change_note=payload.change_note,
            db=db,
        )
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_FORKED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="CourseKit",
        target_id=str(new_kit.id),
        metadata={
            "source_id":   str(kit_id),
            "new_version": new_kit.version,
            "change_note": payload.change_note,
        },
    )
    return CourseKitStatusResponse.model_validate(new_kit)


# ===========================================================================
# Compliance
# ===========================================================================

@router.get("/{kit_id}/compliance", response_model=ComplianceCheckResponse)
async def get_compliance(
    kit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ComplianceCheckResponse:
    try:
        return await CourseKitService.run_compliance_check(kit_id, db=db)
    except KitServiceError as e:
        raise _err(e)


# ===========================================================================
# Export — dispatch, list, and re-download
# ===========================================================================

@router.post("/{kit_id}/export", response_model=KitExportJobResponse, status_code=202)
async def request_export(
    kit_id: UUID,
    payload: KitExportRequest,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> KitExportJobResponse:
    try:
        job_id = await CourseKitService.dispatch_kit_export(
            kit_id=kit_id,
            export_format=payload.format,
            requested_by=current_user.user_id,
            requested_by_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_EXPORT_REQUESTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="CourseKit",
        target_id=str(kit_id),
        metadata={"job_id": job_id, "format": payload.format},
    )
    return KitExportJobResponse(job_id=UUID(job_id), kit_id=kit_id, format=payload.format)


@router.get("/{kit_id}/exports")
async def list_exports(
    kit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[dict]:
    try:
        assets = await CourseKitService.list_exports(kit_id, db=db)
    except KitServiceError as e:
        raise _err(e)
    return [
        {
            "id":                str(a.id),
            "original_filename": a.original_filename,
            "content_type":      a.content_type,
            "size_bytes":        a.size_bytes,
            "created_at":        a.created_at.isoformat(),
        }
        for a in assets
    ]


@router.get("/{kit_id}/exports/{asset_id}/download")
async def get_export_download(
    kit_id: UUID,
    asset_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        asset, url = await CourseKitService.get_export_download(kit_id, asset_id, db=db)
    except KitServiceError as e:
        raise _err(e)
    return {
        "download_url":    url,
        "original_filename": asset.original_filename,
        "size_bytes":      asset.size_bytes,
        "expires_in":      86_400,
    }


# ===========================================================================
# Slides — /reorder must be declared before /{slide_id} to avoid UUID clash
# ===========================================================================

@router.get("/{kit_id}/slides", response_model=list[KitSlideResponse])
async def list_slides(
    kit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[KitSlideResponse]:
    try:
        slides = await CourseKitService.list_slides(kit_id, db=db)
    except KitServiceError as e:
        raise _err(e)
    return [
        _gate_slide(KitSlideResponse.model_validate(s), current_user.role)
        for s in slides
    ]


@router.put("/{kit_id}/slides/reorder", status_code=200)
async def reorder_slides(
    kit_id: UUID,
    payload: KitSlideReorder,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    order_map = {uid: num for uid, num in payload.order}
    try:
        count = await CourseKitService.reorder_slides(kit_id, order_map, db=db)
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_SLIDES_REORDERED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="CourseKit",
        target_id=str(kit_id),
        metadata={"updated": count},
    )
    return {"updated": count}


@router.post("/{kit_id}/slides", response_model=KitSlideResponse, status_code=201)
async def add_slide(
    kit_id: UUID,
    payload: KitSlideCreate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> KitSlideResponse:
    try:
        slide = await CourseKitService.add_slide(kit_id, payload, db=db)
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_SLIDE_ADDED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="KitSlide",
        target_id=str(slide.id),
        metadata={"kit_id": str(kit_id), "slide_number": slide.slide_number},
    )
    return _gate_slide(KitSlideResponse.model_validate(slide), current_user.role)


@router.patch("/{kit_id}/slides/{slide_id}", response_model=KitSlideResponse)
async def update_slide(
    kit_id: UUID,
    slide_id: UUID,
    payload: KitSlideUpdate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> KitSlideResponse:
    try:
        slide = await CourseKitService.update_slide(slide_id, kit_id, payload, db=db)
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_SLIDE_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="KitSlide",
        target_id=str(slide_id),
        metadata={"kit_id": str(kit_id), "changes": payload.model_dump(exclude_none=True)},
    )
    return _gate_slide(KitSlideResponse.model_validate(slide), current_user.role)


@router.delete("/{kit_id}/slides/{slide_id}", status_code=200)
async def delete_slide(
    kit_id: UUID,
    slide_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await CourseKitService.delete_slide(slide_id, kit_id, db=db)
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_SLIDE_DELETED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="KitSlide",
        target_id=str(slide_id),
        metadata={"kit_id": str(kit_id)},
    )
    return {"status": "deleted"}


# ===========================================================================
# Quizlets
# ===========================================================================

@router.get("/{kit_id}/quizlets", response_model=list[KitQuizletResponse])
async def list_quizlets(
    kit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[KitQuizletResponse]:
    try:
        quizlets = await CourseKitService.list_quizlets(kit_id, db=db)
    except KitServiceError as e:
        raise _err(e)
    return [
        _gate_quizlet(KitQuizletResponse.model_validate(q), current_user.role)
        for q in quizlets
    ]


@router.post("/{kit_id}/quizlets", response_model=KitQuizletResponse, status_code=201)
async def add_quizlet(
    kit_id: UUID,
    payload: KitQuizletCreate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> KitQuizletResponse:
    try:
        quizlet = await CourseKitService.add_quizlet(kit_id, payload, db=db)
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_QUIZLET_ADDED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="KitQuizlet",
        target_id=str(quizlet.id),
        metadata={"kit_id": str(kit_id), "question_number": quizlet.question_number},
    )
    return _gate_quizlet(KitQuizletResponse.model_validate(quizlet), current_user.role)


@router.patch("/{kit_id}/quizlets/{quizlet_id}", response_model=KitQuizletResponse)
async def update_quizlet(
    kit_id: UUID,
    quizlet_id: UUID,
    payload: KitQuizletUpdate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> KitQuizletResponse:
    try:
        quizlet = await CourseKitService.update_quizlet(
            quizlet_id, kit_id, payload, db=db
        )
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_QUIZLET_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="KitQuizlet",
        target_id=str(quizlet_id),
        metadata={"kit_id": str(kit_id), "changes": payload.model_dump(exclude_none=True)},
    )
    return _gate_quizlet(KitQuizletResponse.model_validate(quizlet), current_user.role)


@router.delete("/{kit_id}/quizlets/{quizlet_id}", status_code=200)
async def delete_quizlet(
    kit_id: UUID,
    quizlet_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await CourseKitService.delete_quizlet(quizlet_id, kit_id, db=db)
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_QUIZLET_DELETED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="KitQuizlet",
        target_id=str(quizlet_id),
        metadata={"kit_id": str(kit_id)},
    )
    return {"status": "deleted"}


# ===========================================================================
# Assignments
# ===========================================================================

@router.get("/{kit_id}/assignments", response_model=list[KitAssignmentResponse])
async def list_assignments(
    kit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[KitAssignmentResponse]:
    try:
        assignments = await CourseKitService.list_assignments(kit_id, db=db)
    except KitServiceError as e:
        raise _err(e)
    return [
        _gate_assignment(KitAssignmentResponse.model_validate(a), current_user.role)
        for a in assignments
    ]


@router.post("/{kit_id}/assignments", response_model=KitAssignmentResponse, status_code=201)
async def add_assignment(
    kit_id: UUID,
    payload: KitAssignmentCreate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> KitAssignmentResponse:
    try:
        assignment = await CourseKitService.add_assignment(kit_id, payload, db=db)
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_ASSIGNMENT_ADDED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="KitAssignment",
        target_id=str(assignment.id),
        metadata={
            "kit_id":            str(kit_id),
            "assignment_number": assignment.assignment_number,
            "assignment_type":   assignment.assignment_type.value,
        },
    )
    return _gate_assignment(
        KitAssignmentResponse.model_validate(assignment), current_user.role
    )


@router.patch("/{kit_id}/assignments/{assignment_id}", response_model=KitAssignmentResponse)
async def update_assignment(
    kit_id: UUID,
    assignment_id: UUID,
    payload: KitAssignmentUpdate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> KitAssignmentResponse:
    try:
        assignment = await CourseKitService.update_assignment(
            assignment_id, kit_id, payload, db=db
        )
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_ASSIGNMENT_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="KitAssignment",
        target_id=str(assignment_id),
        metadata={"kit_id": str(kit_id), "changes": payload.model_dump(exclude_none=True)},
    )
    return _gate_assignment(
        KitAssignmentResponse.model_validate(assignment), current_user.role
    )


@router.delete("/{kit_id}/assignments/{assignment_id}", status_code=200)
async def delete_assignment(
    kit_id: UUID,
    assignment_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await CourseKitService.delete_assignment(assignment_id, kit_id, db=db)
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_ASSIGNMENT_DELETED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="KitAssignment",
        target_id=str(assignment_id),
        metadata={"kit_id": str(kit_id)},
    )
    return {"status": "deleted"}
