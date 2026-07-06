"""
M03 Course Kit router — RBAC enforced.

RBAC
----
  _WRITE  = ADMIN + (FACULTY role OR active FACULTY grant, e.g. a DEAN with a
            FACULTY grant)  (generate, publish, archive, fork, edit children)
  _READ   = ADMIN + DEAN + FACULTY  (any view)
  _EXPORT = ADMIN + DEAN + FACULTY  (reserved for STEP-11 export endpoints)

Sensitive field gating (DEAN role never sees):
  - KitSlide.speaker_notes → None
  - KitAssignment.model_answer → None

Assignments are the only assessment artifact generated here.

All business logic lives in CourseKitService.
Router is pure HTTP glue: deserialise → call service → audit → serialise.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.dependencies import get_tenant_db_dep, require_roles, require_responsibility, resolve_tenant
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser, TenantInfo
from app.core.rate_limiting import limiter
from app.core.storage.schemas import (
    DownloadUrlResponse,
    GenerateUploadUrlResponse,
    StorageAssetListResponse,
    StorageAssetResponse,
)
from app.modules.m03_course_kit.models import CourseKitStatus
from app.modules.m03_course_kit.schemas import (
    ArchiveRequest,
    ComplianceCheckResponse,
    CourseKitCreate,
    CourseKitDetail,
    CourseKitListItem,
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
    KitResourceConfirmRequest,
    KitResourceUploadUrlRequest,
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
_STUDENT = (TenantRole.STUDENT,)


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

_GATED_ROLES = (TenantRole.DEAN.value, TenantRole.STUDENT.value)


def _gate_slide(slide: KitSlideResponse, role: str) -> KitSlideResponse:
    if role in _GATED_ROLES:
        return slide.model_copy(update={"speaker_notes": None})
    return slide


def _gate_assignment(
    assignment: KitAssignmentResponse, role: str
) -> KitAssignmentResponse:
    if role in _GATED_ROLES:
        return assignment.model_copy(update={"model_answer": None})
    return assignment


def _gate_detail(detail: CourseKitDetail, role: str) -> CourseKitDetail:
    """Null sensitive fields (speaker notes / model answers) for DEAN and STUDENT."""
    if role not in _GATED_ROLES:
        return detail
    return detail.model_copy(update={
        "slides":      [_gate_slide(s, role) for s in detail.slides],
        "assignments": [_gate_assignment(a, role) for a in detail.assignments],
    })


# ---------------------------------------------------------------------------
# Student self-service — read-only, PUBLISHED kits for enrolled courses only.
# Declared before the generic "/{kit_id}" route so the literal "/student"
# path segment matches first (see the slides /reorder comment below for the
# same FastAPI routing pitfall).
# ---------------------------------------------------------------------------

async def _student_syllabus_ids(user_id: UUID, db: AsyncSession) -> set[UUID]:
    from app.modules.m11_sis.student_academic_repository import get_student_enrolled_syllabus_ids
    return await get_student_enrolled_syllabus_ids(user_id, db)


async def _require_student_published_kit(kit_id: UUID, student_user_id: UUID, db: AsyncSession):
    kit = await CourseKitService.get_kit(kit_id, db=db)
    if kit is None or kit.status != CourseKitStatus.PUBLISHED:
        raise _404()
    allowed = await _student_syllabus_ids(student_user_id, db)
    if kit.syllabus_id not in allowed:
        raise _404()
    return kit


@router.get("/student", response_model=CourseKitListResponse)
async def student_list_kits(
    syllabus_id: UUID = Query(..., description="Syllabus to list published kits for"),
    unit_number: int | None = Query(None, description="Optionally filter to one unit"),
    current_user: CurrentUser = Depends(require_roles(*_STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitListResponse:
    allowed = await _student_syllabus_ids(current_user.user_id, db)
    if syllabus_id not in allowed:
        raise HTTPException(
            status_code=403,
            detail={"error": "FORBIDDEN", "message": "You are not enrolled in this subject."},
        )

    total, items = await CourseKitService.list_kits(
        syllabus_id=syllabus_id,
        status_filter=CourseKitStatus.PUBLISHED,
        page=1,
        page_size=200,
        db=db,
    )
    if unit_number is not None:
        items = [k for k in items if k.unit_number == unit_number]
        total = len(items)

    cp_map = await _course_program_map(list({k.syllabus_id for k in items}), db=db)
    enriched = []
    for k in items:
        base = CourseKitResponse.model_validate(k)
        course, program = cp_map.get(k.syllabus_id, (None, None))
        enriched.append(CourseKitListItem(
            **base.model_dump(),
            course_title=course.title if course else None,
            course_code=course.code if course else None,
            program_name=program.title if program else None,
            semester=course.semester if course else None,
        ))

    return CourseKitListResponse(total=total, page=1, page_size=len(enriched) or 1, items=enriched)


@router.get("/student/{kit_id}", response_model=CourseKitDetail)
async def student_get_kit(
    kit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitDetail:
    kit = await CourseKitService.get_kit_detail(kit_id, db=db)
    if kit is None or kit.status != CourseKitStatus.PUBLISHED:
        raise _404()
    allowed = await _student_syllabus_ids(current_user.user_id, db)
    if kit.syllabus_id not in allowed:
        raise _404()

    detail = CourseKitDetail.model_validate(kit)
    cp_map = await _course_program_map([kit.syllabus_id], db=db)
    course, program = cp_map.get(kit.syllabus_id, (None, None))
    if course:
        detail = detail.model_copy(update={
            "course_title": course.title,
            "course_code":  course.code,
            "program_name": program.title if program else None,
            "semester":     course.semester,
        })
    return _gate_detail(detail, current_user.role)


@router.get("/student/{kit_id}/resources", response_model=StorageAssetListResponse)
async def student_list_resources(
    kit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> StorageAssetListResponse:
    await _require_student_published_kit(kit_id, current_user.user_id, db)
    items = await CourseKitService.list_resources(kit_id, db=db)
    return StorageAssetListResponse(total=len(items), page=1, page_size=len(items) or 1, items=items)


@router.get(
    "/student/{kit_id}/resources/{asset_id}/download-url", response_model=DownloadUrlResponse
)
async def student_get_resource_download_url(
    kit_id: UUID,
    asset_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> DownloadUrlResponse:
    from app.config import settings

    await _require_student_published_kit(kit_id, current_user.user_id, db)
    try:
        presigned_url = await CourseKitService.get_resource_download_url(kit_id, asset_id, db=db)
    except KitServiceError as e:
        raise _err(e)
    return DownloadUrlResponse(
        presigned_url=presigned_url,
        expires_in_seconds=settings.PRESIGNED_URL_EXPIRY_MINUTES_GET * 60,
    )


# ===========================================================================
# Kit CRUD
# ===========================================================================

@router.post("", response_model=CourseKitResponse, status_code=201)
async def create_kit(
    payload: CourseKitCreate,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
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


async def _course_program_map(
    syllabus_ids: list[UUID], *, db: AsyncSession
) -> dict[UUID, tuple]:
    """Bulk-resolve syllabus_id -> (course, program), mirroring the Syllabus
    module's list/detail name-resolution pattern (M02 router.py)."""
    from sqlalchemy import select
    from app.modules.m01_program_advisor.models import Course, Program
    from app.modules.m02_syllabus.models import Syllabus

    if not syllabus_ids:
        return {}

    syllabi_result = await db.execute(select(Syllabus).where(Syllabus.id.in_(syllabus_ids)))
    syllabi = syllabi_result.scalars().all()
    syllabus_map = {s.id: s for s in syllabi}

    cids = list({s.course_id for s in syllabi})
    course_map: dict = {}
    if cids:
        courses_result = await db.execute(select(Course).where(Course.id.in_(cids)))
        courses = courses_result.scalars().all()
        course_map = {c.id: c for c in courses}
        pids = list({c.program_id for c in courses})
        program_map: dict = {}
        if pids:
            programs_result = await db.execute(select(Program).where(Program.id.in_(pids)))
            program_map = {p.id: p for p in programs_result.scalars().all()}
    else:
        program_map = {}

    result: dict[UUID, tuple] = {}
    for syllabus_id, syllabus in syllabus_map.items():
        course = course_map.get(syllabus.course_id)
        program = program_map.get(course.program_id) if course else None
        result[syllabus_id] = (course, program)
    return result


@router.get("", response_model=CourseKitListResponse)
async def list_kits(
    syllabus_id: UUID | None = Query(None, description="Filter by syllabus; omit to list all"),
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
        caller_role=current_user.role,
        faculty_user_id=current_user.user_id,
        db=db,
    )

    cp_map = await _course_program_map(list({k.syllabus_id for k in items}), db=db)

    enriched = []
    for k in items:
        base = CourseKitResponse.model_validate(k)
        course, program = cp_map.get(k.syllabus_id, (None, None))
        enriched.append(CourseKitListItem(
            **base.model_dump(),
            course_title=course.title if course else None,
            course_code=course.code if course else None,
            program_name=program.title if program else None,
            semester=course.semester if course else None,
        ))

    return CourseKitListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=enriched,
    )


@router.get("/{kit_id}", response_model=CourseKitDetail)
async def get_kit(
    kit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitDetail:
    kit = await CourseKitService.get_kit_detail(
        kit_id, caller_role=current_user.role, faculty_user_id=current_user.user_id, db=db
    )
    if kit is None:
        raise _404()
    detail = CourseKitDetail.model_validate(kit)

    cp_map = await _course_program_map([kit.syllabus_id], db=db)
    course, program = cp_map.get(kit.syllabus_id, (None, None))
    if course:
        detail = detail.model_copy(update={
            "course_title": course.title,
            "course_code":  course.code,
            "program_name": program.title if program else None,
            "semester":     course.semester,
        })

    return _gate_detail(detail, current_user.role)


@router.get("/{kit_id}/status", response_model=CourseKitStatusResponse)
async def get_kit_status(
    kit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitStatusResponse:
    kit = await CourseKitService.get_kit(
        kit_id, caller_role=current_user.role, faculty_user_id=current_user.user_id, db=db
    )
    if kit is None:
        raise _404()
    return CourseKitStatusResponse.model_validate(kit)


@router.patch("/{kit_id}", response_model=CourseKitResponse)
async def update_kit(
    kit_id: UUID,
    payload: CourseKitUpdate,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitResponse:
    try:
        kit = await CourseKitService.update_kit(
            kit_id, payload,
            caller_role=current_user.role, faculty_user_id=current_user.user_id,
            db=db,
        )
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await CourseKitService.delete_kit(
            kit_id,
            caller_role=current_user.role, faculty_user_id=current_user.user_id,
            db=db,
        )
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
    kit = await CourseKitService.get_kit(
        kit_id, caller_role=current_user.role, faculty_user_id=current_user.user_id, db=db
    )
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
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
                caller_role=current_user.role, faculty_user_id=current_user.user_id,
                db=db,
            )
        except KitServiceError as e:
            raise _err(e)

    try:
        job_id = await CourseKitService.dispatch_kit_generation(
            kit_id=kit_id,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            caller_role=current_user.role,
            faculty_user_id=current_user.user_id,
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitStatusResponse:
    try:
        kit = await CourseKitService.publish_kit(
            kit_id, published_by=current_user.user_id,
            caller_role=current_user.role, faculty_user_id=current_user.user_id,
            db=db,
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitStatusResponse:
    try:
        kit = await CourseKitService.archive_kit(
            kit_id, caller_role=current_user.role, faculty_user_id=current_user.user_id, db=db
        )
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseKitStatusResponse:
    try:
        new_kit = await CourseKitService.fork_kit(
            kit_id,
            forked_by=current_user.user_id,
            change_note=payload.change_note,
            caller_role=current_user.role,
            faculty_user_id=current_user.user_id,
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
        return await CourseKitService.run_compliance_check(
            kit_id, caller_role=current_user.role, faculty_user_id=current_user.user_id, db=db
        )
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
            caller_role=current_user.role,
            faculty_user_id=current_user.user_id,
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
        assets = await CourseKitService.list_exports(
            kit_id, caller_role=current_user.role, faculty_user_id=current_user.user_id, db=db
        )
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
        asset, url = await CourseKitService.get_export_download(
            kit_id, asset_id,
            caller_role=current_user.role, faculty_user_id=current_user.user_id,
            db=db,
        )
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
        slides = await CourseKitService.list_slides(
            kit_id, caller_role=current_user.role, faculty_user_id=current_user.user_id, db=db
        )
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    order_map = {uid: num for uid, num in payload.order}
    try:
        count = await CourseKitService.reorder_slides(
            kit_id, order_map,
            caller_role=current_user.role, faculty_user_id=current_user.user_id,
            db=db,
        )
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> KitSlideResponse:
    try:
        slide = await CourseKitService.add_slide(
            kit_id, payload,
            caller_role=current_user.role, faculty_user_id=current_user.user_id,
            db=db,
        )
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> KitSlideResponse:
    try:
        slide = await CourseKitService.update_slide(
            slide_id, kit_id, payload,
            caller_role=current_user.role, faculty_user_id=current_user.user_id,
            db=db,
        )
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await CourseKitService.delete_slide(
            slide_id, kit_id,
            caller_role=current_user.role, faculty_user_id=current_user.user_id,
            db=db,
        )
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
# Assignments
# ===========================================================================

@router.get("/{kit_id}/assignments", response_model=list[KitAssignmentResponse])
async def list_assignments(
    kit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[KitAssignmentResponse]:
    try:
        assignments = await CourseKitService.list_assignments(
            kit_id, caller_role=current_user.role, faculty_user_id=current_user.user_id, db=db
        )
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> KitAssignmentResponse:
    try:
        assignment = await CourseKitService.add_assignment(
            kit_id, payload,
            caller_role=current_user.role, faculty_user_id=current_user.user_id,
            db=db,
        )
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> KitAssignmentResponse:
    try:
        assignment = await CourseKitService.update_assignment(
            assignment_id, kit_id, payload,
            caller_role=current_user.role, faculty_user_id=current_user.user_id,
            db=db,
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await CourseKitService.delete_assignment(
            assignment_id, kit_id,
            caller_role=current_user.role, faculty_user_id=current_user.user_id,
            db=db,
        )
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


# ===========================================================================
# Faculty-uploaded resources (PDF/PPT/DOCX/notes) — reuses the generic
# storage module (backend/app/core/storage/); this router only adds
# Course-Kit-specific RBAC and kit-ownership checks. See service.py.
# ===========================================================================

@router.post("/{kit_id}/resources/upload-url", response_model=GenerateUploadUrlResponse)
async def generate_resource_upload_url(
    kit_id: UUID,
    payload: KitResourceUploadUrlRequest,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    tenant_info: TenantInfo = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> GenerateUploadUrlResponse:
    try:
        return await CourseKitService.generate_resource_upload_url(
            kit_id,
            payload,
            tenant_slug=tenant_info.slug,
            current_user_id=current_user.user_id,
            caller_role=current_user.role,
            faculty_user_id=current_user.user_id,
            db=db,
        )
    except KitServiceError as e:
        raise _err(e)


@router.post("/{kit_id}/resources", response_model=StorageAssetResponse, status_code=201)
async def add_resource(
    kit_id: UUID,
    payload: KitResourceConfirmRequest,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    tenant_info: TenantInfo = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> StorageAssetResponse:
    try:
        asset = await CourseKitService.add_resource(
            kit_id,
            payload,
            tenant_id=tenant_info.id,
            tenant_slug=tenant_info.slug,
            current_user_id=current_user.user_id,
            caller_role=current_user.role,
            faculty_user_id=current_user.user_id,
            db=db,
        )
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_RESOURCE_UPLOADED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="StorageAsset",
        target_id=str(asset.id),
        metadata={
            "kit_id": str(kit_id),
            "original_filename": asset.original_filename,
            "content_type": asset.content_type,
            "size_bytes": asset.size_bytes,
        },
    )
    return asset


@router.get("/{kit_id}/resources", response_model=StorageAssetListResponse)
async def list_resources(
    kit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> StorageAssetListResponse:
    try:
        items = await CourseKitService.list_resources(
            kit_id, caller_role=current_user.role, faculty_user_id=current_user.user_id, db=db
        )
    except KitServiceError as e:
        raise _err(e)
    return StorageAssetListResponse(
        total=len(items), page=1, page_size=len(items), items=items
    )


@router.get(
    "/{kit_id}/resources/{asset_id}/download-url", response_model=DownloadUrlResponse
)
async def get_resource_download_url(
    kit_id: UUID,
    asset_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> DownloadUrlResponse:
    from app.config import settings

    try:
        presigned_url = await CourseKitService.get_resource_download_url(
            kit_id, asset_id,
            caller_role=current_user.role, faculty_user_id=current_user.user_id,
            db=db,
        )
    except KitServiceError as e:
        raise _err(e)
    return DownloadUrlResponse(
        presigned_url=presigned_url,
        expires_in_seconds=settings.PRESIGNED_URL_EXPIRY_MINUTES_GET * 60,
    )


@router.delete("/{kit_id}/resources/{asset_id}", status_code=200)
async def delete_resource(
    kit_id: UUID,
    asset_id: UUID,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await CourseKitService.delete_resource(
            kit_id, asset_id,
            caller_role=current_user.role, faculty_user_id=current_user.user_id,
            db=db,
        )
    except KitServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.COURSE_KIT_RESOURCE_DELETED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="StorageAsset",
        target_id=str(asset_id),
        metadata={"kit_id": str(kit_id)},
    )
    return {"status": "deleted"}
