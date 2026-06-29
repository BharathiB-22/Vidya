"""
M02 Syllabus router — ~33 endpoints, RBAC enforced.

RBAC
----
  _WRITE  = ADMIN + FACULTY   create / edit / generate / approve / reject / fork
  _READ   = ADMIN + DEAN + FACULTY   any view
  _LOCK   = ADMIN + DEAN   lock / unlock (semester gate, not content approval)
  _EXPORT = ADMIN + DEAN + FACULTY   export (same population as _READ)

All business logic lives in SyllabusService.
Router is pure HTTP glue: deserialise → call service → audit → serialise.
"""
from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("vidya.router.m02")

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.rate_limiting import limiter
from app.modules.m02_syllabus.schemas import (
    ApproveRequest,
    COPOMappingBulkUpdate,
    COPOMappingResponse,
    COPOMatrixResponse,
    ComplianceCheckResponse,
    CourseOutcomeCreate,
    CourseOutcomeResponse,
    CourseOutcomeUpdate,
    ForkRequest,
    GenerateSyllabusRequest,
    LockRequest,
    ReferenceCandidate,
    RejectRequest,
    RequestRevisionRequest,
    SyllabusAIJobResponse,
    SyllabusCreate,
    SyllabusDetail,
    SyllabusExportJobResponse,
    SyllabusDeanItem,
    SyllabusDeanOverviewResponse,
    SyllabusListItem,
    SyllabusListResponse,
    SyllabusReferenceCreate,
    SyllabusReferenceResponse,
    SyllabusReferenceUpdate,
    SyllabusResponse,
    SyllabusStatusResponse,
    SyllabusUnitCreate,
    SyllabusUnitReorder,
    SyllabusUnitResponse,
    SyllabusUnitUpdate,
    SyllabusUpdate,
    SyllabusVersionResponse,
    ReferenceSearchRequest,
)
from app.modules.m02_syllabus.models import RefType, SyllabusStatus
from app.modules.m02_syllabus.service import SyllabusService, SyllabusServiceError

router = APIRouter(tags=["syllabi"])

# ---------------------------------------------------------------------------
# RBAC role sets
#   _WRITE  — create, edit, generate, submit-for-review (FACULTY + ADMIN)
#   _READ   — view (all content roles)
#   _DEAN   — approve, reject (DEAN only — academic governance)
#   _LOCK   — lock, unlock semester (DEAN only)
#   _EXPORT — export approved syllabi
# ---------------------------------------------------------------------------
_WRITE  = (TenantRole.ADMIN, TenantRole.FACULTY)
_READ   = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)
_DEAN   = (TenantRole.DEAN,)
_LOCK   = (TenantRole.DEAN,)
_EXPORT = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)


async def _lookup_user(user_id, *, db: AsyncSession) -> dict:
    """Return {email, full_name} for a user_id or empty dict if not found."""
    from sqlalchemy import text as _text
    result = await db.execute(
        _text("SELECT email, full_name FROM users WHERE id = :uid"),
        {"uid": str(user_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else {}


def _err(e: SyllabusServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


def _404(entity: str = "Syllabus") -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": "NOT_FOUND", "message": f"{entity} not found."},
    )


# ===========================================================================
# Syllabus CRUD
# ===========================================================================

@router.post("", response_model=SyllabusResponse, status_code=201)
async def create_syllabus(
    payload: SyllabusCreate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusResponse:
    try:
        syllabus = await SyllabusService.create_syllabus(
            payload,
            created_by=current_user.user_id,
            creator_role=current_user.role,
            db=db,
        )
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_CREATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Syllabus",
        target_id=str(syllabus.id),
        metadata={"course_id": str(syllabus.course_id), "version": syllabus.version},
    )
    return SyllabusResponse.model_validate(syllabus)


@router.get("", response_model=SyllabusListResponse)
async def list_syllabi(
    course_id: UUID | None = Query(None, description="Filter by course; omit to list all"),
    status: SyllabusStatus | None = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusListResponse:
    from sqlalchemy import select
    from app.modules.m01_program_advisor.models import Course, Program

    try:
        total, items = await SyllabusService.list_syllabi(
            course_id=course_id,
            status_filter=status,
            page=page,
            page_size=page_size,
            caller_role=current_user.role,
            faculty_user_id=current_user.user_id,
            db=db,
        )
    except SyllabusServiceError as e:
        raise _err(e)

    # Bulk-fetch courses and programs for enrichment
    cids = list({s.course_id for s in items})
    course_map: dict = {}
    program_map: dict = {}
    if cids:
        courses_result = await db.execute(select(Course).where(Course.id.in_(cids)))
        courses = courses_result.scalars().all()
        course_map = {c.id: c for c in courses}
        pids = list({c.program_id for c in courses})
        if pids:
            programs_result = await db.execute(select(Program).where(Program.id.in_(pids)))
            program_map = {p.id: p for p in programs_result.scalars().all()}

    enriched = []
    for s in items:
        base = SyllabusResponse.model_validate(s)
        course = course_map.get(s.course_id)
        program = program_map.get(course.program_id) if course else None
        enriched.append(SyllabusListItem(
            **base.model_dump(),
            course_title=course.title if course else "Unknown Course",
            course_code=course.code if course else "—",
            program_name=program.title if program else "Unknown Program",
            semester=course.semester if course else 0,
        ))

    return SyllabusListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=enriched,
    )


@router.get("/dean-overview", response_model=SyllabusDeanOverviewResponse)
async def dean_overview(
    status: list[str] = Query(
        default=["PENDING_REVIEW", "REJECTED", "DEAN_APPROVED", "DEAN_LOCKED"],
        description="Status filter (multi-value). Default: pending + rejected + approved + locked.",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN, TenantRole.ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusDeanOverviewResponse:
    """Return enriched syllabus rows for the Dean review dashboard.

    Joins course code/title + faculty name from the tenant users table.
    """
    from sqlalchemy import text, func, select
    from app.modules.m02_syllabus.models import Syllabus, CourseOutcome, SyllabusUnit
    from app.modules.m01_program_advisor.models import Course

    offset = (page - 1) * page_size

    # Base query: syllabuses filtered by status
    # Dean overview defaults include REJECTED so deans see what they sent back.
    stmt = (
        select(Syllabus)
        .where(Syllabus.status.in_(status))
        .order_by(Syllabus.updated_at.desc().nullslast(), Syllabus.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    syllabuses = result.scalars().all()

    count_stmt = select(func.count(Syllabus.id)).where(Syllabus.status.in_(status))
    total = (await db.execute(count_stmt)).scalar_one()

    if not syllabuses:
        return SyllabusDeanOverviewResponse(total=total, items=[])

    # Bulk-fetch courses
    course_ids = list({s.course_id for s in syllabuses})
    courses_result = await db.execute(select(Course).where(Course.id.in_(course_ids)))
    course_map = {c.id: c for c in courses_result.scalars().all()}

    # Bulk-fetch faculty names from tenant users table
    user_ids = list({str(s.created_by_user_id) for s in syllabuses})
    user_rows = (await db.execute(
        text("SELECT id::text, full_name, email FROM users WHERE id = ANY(:ids)"),
        {"ids": user_ids},
    )).mappings().all()
    user_map = {r["id"]: r for r in user_rows}

    # Bulk-fetch unit counts
    unit_counts_result = await db.execute(
        select(SyllabusUnit.syllabus_id, func.count(SyllabusUnit.id).label("cnt"))
        .where(SyllabusUnit.syllabus_id.in_([s.id for s in syllabuses]))
        .group_by(SyllabusUnit.syllabus_id)
    )
    unit_count_map = {row.syllabus_id: row.cnt for row in unit_counts_result}

    # Bulk-fetch CO counts
    co_counts_result = await db.execute(
        select(CourseOutcome.syllabus_id, func.count(CourseOutcome.id).label("cnt"))
        .where(CourseOutcome.syllabus_id.in_([s.id for s in syllabuses]))
        .group_by(CourseOutcome.syllabus_id)
    )
    co_count_map = {row.syllabus_id: row.cnt for row in co_counts_result}

    items = []
    for s in syllabuses:
        course = course_map.get(s.course_id)
        u_id = str(s.created_by_user_id)
        user = user_map.get(u_id, {})
        items.append(SyllabusDeanItem(
            id=s.id,
            status=s.status,
            version=s.version,
            course_id=s.course_id,
            course_code=course.code if course else "—",
            course_title=course.title if course else "Unknown Course",
            faculty_name=user.get("full_name"),
            faculty_email=user.get("email"),
            unit_count=unit_count_map.get(s.id, 0),
            co_count=co_count_map.get(s.id, 0),
            dean_comment=s.dean_comment,
            created_at=s.created_at,
            updated_at=s.updated_at,
        ))

    return SyllabusDeanOverviewResponse(total=total, items=items)


@router.get("/{syllabus_id}", response_model=SyllabusDetail)
async def get_syllabus(
    syllabus_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusDetail:
    from sqlalchemy import select
    from app.modules.m01_program_advisor.models import Course, Program

    syllabus = await SyllabusService.get_syllabus_detail(syllabus_id, db=db)
    if syllabus is None:
        raise _404()

    detail = SyllabusDetail.model_validate(syllabus)

    course_result = await db.execute(select(Course).where(Course.id == syllabus.course_id))
    course = course_result.scalar_one_or_none()
    if course:
        program_result = await db.execute(select(Program).where(Program.id == course.program_id))
        program = program_result.scalar_one_or_none()
        detail = detail.model_copy(update={
            "course_title": course.title,
            "course_code":  course.code,
            "program_name": program.title if program else "Unknown Program",
            "semester":     course.semester,
        })

    return detail


@router.get("/{syllabus_id}/status", response_model=SyllabusStatusResponse)
async def get_syllabus_status(
    syllabus_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusStatusResponse:
    syllabus = await SyllabusService.get_syllabus(syllabus_id, db=db)
    if syllabus is None:
        raise _404()
    return SyllabusStatusResponse.model_validate(syllabus)


@router.patch("/{syllabus_id}", response_model=SyllabusResponse)
async def update_syllabus(
    syllabus_id: UUID,
    payload: SyllabusUpdate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusResponse:
    try:
        syllabus = await SyllabusService.update_syllabus(syllabus_id, payload, db=db)
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Syllabus",
        target_id=str(syllabus_id),
        metadata={"changes": payload.model_dump(exclude_none=True)},
    )
    return SyllabusResponse.model_validate(syllabus)


@router.delete("/{syllabus_id}", status_code=200)
async def delete_syllabus(
    syllabus_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await SyllabusService.delete_syllabus(
            syllabus_id, caller_role=current_user.role, db=db
        )
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_DELETED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Syllabus",
        target_id=str(syllabus_id),
        metadata={"syllabus_id": str(syllabus_id)},
    )
    return {"status": "deleted"}


@router.get("/{syllabus_id}/versions", response_model=list[SyllabusVersionResponse])
async def list_syllabus_versions(
    syllabus_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[SyllabusVersionResponse]:
    # Load the syllabus to get its course_id, then list all versions for that course.
    syllabus = await SyllabusService.get_syllabus(syllabus_id, db=db)
    if syllabus is None:
        raise _404()
    versions = await SyllabusService.list_versions(syllabus.course_id, db=db)
    return [SyllabusVersionResponse.model_validate(v) for v in versions]


# ===========================================================================
# AI generation
# ===========================================================================

@router.post("/{syllabus_id}/generate", response_model=SyllabusAIJobResponse)
@limiter.limit("5/minute")
async def generate_syllabus(
    request: Request,
    syllabus_id: UUID,
    payload: GenerateSyllabusRequest,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusAIJobResponse:
    # If caller provides updated instructions, persist them first (DRAFT guard in service).
    if payload.custom_instructions is not None:
        try:
            await SyllabusService.update_syllabus(
                syllabus_id,
                SyllabusUpdate(custom_instructions=payload.custom_instructions),
                db=db,
            )
        except SyllabusServiceError as e:
            raise _err(e)
    try:
        job_id = await SyllabusService.dispatch_ai_generation(
            syllabus_id=syllabus_id,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_GENERATION_QUEUED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Syllabus",
        target_id=str(syllabus_id),
        metadata={"job_id": job_id},
    )
    return SyllabusAIJobResponse(job_id=UUID(job_id), syllabus_id=syllabus_id)


@router.get("/{syllabus_id}/jobs/{job_id}")
async def get_generation_job(
    syllabus_id: UUID,
    job_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    job = await SyllabusService.get_job_status(
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

@router.post("/{syllabus_id}/submit-for-review", response_model=SyllabusStatusResponse)
async def submit_syllabus_for_review(
    syllabus_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusStatusResponse:
    """DRAFT → PENDING_REVIEW. Faculty submits syllabus for Dean approval."""
    try:
        syllabus = await SyllabusService.submit_for_review(
            syllabus_id, submitted_by=current_user.user_id, db=db
        )
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_APPROVED,  # reuse closest event type
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Syllabus",
        target_id=str(syllabus_id),
        metadata={"action": "SUBMIT_FOR_REVIEW", "version": syllabus.version},
    )
    return SyllabusStatusResponse.model_validate(syllabus)


@router.post("/{syllabus_id}/resubmit", response_model=SyllabusStatusResponse)
async def resubmit_syllabus(
    syllabus_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusStatusResponse:
    """REJECTED → PENDING_REVIEW. Faculty resubmits after addressing Dean feedback."""
    try:
        syllabus = await SyllabusService.resubmit(
            syllabus_id, submitted_by=current_user.user_id, db=db
        )
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_RESUBMITTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Syllabus",
        target_id=str(syllabus_id),
        metadata={"version": syllabus.version},
    )
    return SyllabusStatusResponse.model_validate(syllabus)


@router.post("/{syllabus_id}/approve", response_model=SyllabusStatusResponse)
async def approve_syllabus(
    syllabus_id: UUID,
    payload: ApproveRequest,
    current_user: CurrentUser = Depends(require_roles(*_DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusStatusResponse:
    """PENDING_REVIEW → DEAN_APPROVED. Dean approves faculty-submitted syllabus."""
    try:
        syllabus = await SyllabusService.approve(
            syllabus_id, approved_by=current_user.user_id, db=db
        )
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_APPROVED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Syllabus",
        target_id=str(syllabus_id),
        metadata={"action": "DEAN_APPROVED", "version": syllabus.version, "comment": payload.comment},
    )
    try:
        from app.core.notifications.service import NotificationService
        from app.core.notifications.models import NotificationType
        faculty = await _lookup_user(syllabus.created_by_user_id, db=db)
        await NotificationService.send(
            NotificationType.SYLLABUS_APPROVED,
            recipient_user_id=syllabus.created_by_user_id,
            recipient_email=faculty.get("email"),
            title="Syllabus Approved",
            body=f"Your syllabus (v{syllabus.version}) has been approved by the Dean."
                 + (f" Note: {payload.comment}" if payload.comment else ""),
            entity_type="Syllabus",
            entity_id=str(syllabus_id),
            db=db,
        )
    except Exception:
        logger.warning("m02.approve: notification failed (non-blocking)", exc_info=True)
    return SyllabusStatusResponse.model_validate(syllabus)


@router.post("/{syllabus_id}/reject", response_model=SyllabusStatusResponse)
async def reject_syllabus(
    syllabus_id: UUID,
    payload: RejectRequest,
    current_user: CurrentUser = Depends(require_roles(*_DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusStatusResponse:
    """PENDING_REVIEW → REJECTED. Dean rejects syllabus; faculty can edit and resubmit."""
    try:
        syllabus = await SyllabusService.reject(
            syllabus_id,
            reason=payload.reason,
            db=db,
        )
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_REJECTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Syllabus",
        target_id=str(syllabus_id),
        metadata={"reason": payload.reason, "version": syllabus.version},
    )
    # Notify the faculty who created the syllabus
    try:
        from app.core.notifications.service import NotificationService
        from app.core.notifications.models import NotificationType
        faculty = await _lookup_user(syllabus.created_by_user_id, db=db)
        await NotificationService.send(
            NotificationType.SYLLABUS_REJECTED,
            recipient_user_id=syllabus.created_by_user_id,
            recipient_email=faculty.get("email"),
            title="Syllabus Rejected",
            body=f"Your syllabus (v{syllabus.version}) was rejected by the Dean. Reason: {payload.reason}",
            entity_type="Syllabus",
            entity_id=str(syllabus_id),
            db=db,
        )
    except Exception:
        logger.warning("m02.reject: notification failed (non-blocking)", exc_info=True)
    return SyllabusStatusResponse.model_validate(syllabus)


@router.post("/{syllabus_id}/request-revision", response_model=SyllabusStatusResponse)
async def request_revision(
    syllabus_id: UUID,
    payload: RequestRevisionRequest,
    current_user: CurrentUser = Depends(require_roles(*_DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusStatusResponse:
    """PENDING_REVIEW → REJECTED (revision type). Dean requests specific changes."""
    try:
        syllabus = await SyllabusService.request_revision(
            syllabus_id,
            comments=payload.comments,
            db=db,
        )
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_REVISION_REQUESTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Syllabus",
        target_id=str(syllabus_id),
        metadata={"comments": payload.comments, "version": syllabus.version},
    )
    try:
        from app.core.notifications.service import NotificationService
        from app.core.notifications.models import NotificationType
        faculty = await _lookup_user(syllabus.created_by_user_id, db=db)
        await NotificationService.send(
            NotificationType.SYLLABUS_REVISION_REQUESTED,
            recipient_user_id=syllabus.created_by_user_id,
            recipient_email=faculty.get("email"),
            title="Syllabus Revision Requested",
            body=f"The Dean has requested revisions to your syllabus (v{syllabus.version}): {payload.comments}",
            entity_type="Syllabus",
            entity_id=str(syllabus_id),
            db=db,
        )
    except Exception:
        logger.warning("m02.request_revision: notification failed (non-blocking)", exc_info=True)
    return SyllabusStatusResponse.model_validate(syllabus)


@router.post("/{syllabus_id}/lock", response_model=SyllabusStatusResponse)
async def lock_syllabus(
    syllabus_id: UUID,
    payload: LockRequest,
    current_user: CurrentUser = Depends(require_roles(*_LOCK)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusStatusResponse:
    try:
        syllabus = await SyllabusService.lock(
            syllabus_id, locked_by=current_user.user_id, db=db
        )
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_LOCKED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Syllabus",
        target_id=str(syllabus_id),
        metadata={"version": syllabus.version, "comment": payload.comment},
    )

    # M05 hook — mark related learning packages OUTDATED when syllabus is locked.
    # Deferred import avoids circular dependency (M02 ↔ M05).
    # Non-blocking: a bump failure must not prevent the lock from succeeding.
    try:
        from app.modules.m05_learning_materials.service import LearningPackageService
        outdated_count = await LearningPackageService.on_syllabus_version_bump(
            syllabus_id, db=db
        )
        if outdated_count > 0:
            logger.info(
                "m02.lock: %d M05 package(s) marked OUTDATED (syllabus=%s)",
                outdated_count, syllabus_id,
            )
            await AuditService.log(
                AuditEventType.LEARNING_PACKAGE_OUTDATED_BY_SYLLABUS_BUMP,
                actor_user_id=current_user.user_id,
                actor_role=current_user.role,
                tenant_id=current_user.tenant_id,
                schema_name=current_user.schema_name,
                target_entity="Syllabus",
                target_id=str(syllabus_id),
                metadata={"outdated_packages": outdated_count, "syllabus_version": syllabus.version},
            )
    except Exception as exc:
        logger.warning(
            "m02.lock: M05 syllabus bump failed (non-blocking) syllabus=%s: %s",
            syllabus_id, exc,
        )

    return SyllabusStatusResponse.model_validate(syllabus)


@router.post("/{syllabus_id}/unlock", response_model=SyllabusStatusResponse)
async def unlock_syllabus(
    syllabus_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_LOCK)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusStatusResponse:
    try:
        syllabus = await SyllabusService.unlock(syllabus_id, db=db)
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_UNLOCKED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Syllabus",
        target_id=str(syllabus_id),
        metadata={"syllabus_id": str(syllabus_id)},
    )
    return SyllabusStatusResponse.model_validate(syllabus)


@router.post("/{syllabus_id}/fork", response_model=SyllabusStatusResponse, status_code=201)
async def fork_syllabus(
    syllabus_id: UUID,
    payload: ForkRequest,
    current_user: CurrentUser = Depends(require_roles(*_WRITE, TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusStatusResponse:
    try:
        new_syllabus = await SyllabusService.fork(
            syllabus_id,
            created_by=current_user.user_id,
            change_note=payload.change_note,
            db=db,
        )
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_FORKED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Syllabus",
        target_id=str(new_syllabus.id),
        metadata={
            "source_id":   str(syllabus_id),
            "new_id":      str(new_syllabus.id),
            "new_version": new_syllabus.version,
            "change_note": payload.change_note,
        },
    )
    # If Dean created this fork, notify the faculty who owns the course
    if current_user.role == "DEAN":
        try:
            from app.core.notifications.service import NotificationService
            from app.core.notifications.models import NotificationType
            faculty = await _lookup_user(new_syllabus.created_by_user_id, db=db)
            await NotificationService.send(
                NotificationType.SYLLABUS_VERSION_CREATED,
                recipient_user_id=new_syllabus.created_by_user_id,
                recipient_email=faculty.get("email"),
                title="New Syllabus Version Created",
                body=f"The Dean created a new draft version (v{new_syllabus.version}) of your syllabus for revision."
                     + (f" Note: {payload.change_note}" if payload.change_note else ""),
                entity_type="Syllabus",
                entity_id=str(new_syllabus.id),
                db=db,
            )
        except Exception:
            logger.warning("m02.fork: notification failed (non-blocking)", exc_info=True)
    return SyllabusStatusResponse.model_validate(new_syllabus)


# ===========================================================================
# Compliance
# ===========================================================================

@router.get("/{syllabus_id}/compliance", response_model=ComplianceCheckResponse)
async def get_compliance(
    syllabus_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ComplianceCheckResponse:
    try:
        return await SyllabusService.run_compliance_check(syllabus_id, db=db)
    except SyllabusServiceError as e:
        raise _err(e)


# ===========================================================================
# Course Outcomes
# ===========================================================================

@router.get("/{syllabus_id}/outcomes", response_model=list[CourseOutcomeResponse])
async def list_outcomes(
    syllabus_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[CourseOutcomeResponse]:
    cos = await SyllabusService.list_cos(syllabus_id, db=db)
    return [CourseOutcomeResponse.model_validate(c) for c in cos]


@router.post("/{syllabus_id}/outcomes", response_model=CourseOutcomeResponse, status_code=201)
async def add_outcome(
    syllabus_id: UUID,
    payload: CourseOutcomeCreate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseOutcomeResponse:
    try:
        co = await SyllabusService.add_co(syllabus_id, payload, db=db)
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_CO_ADDED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="CourseOutcome",
        target_id=str(co.id),
        metadata={"syllabus_id": str(syllabus_id), "code": co.code},
    )
    return CourseOutcomeResponse.model_validate(co)


@router.patch(
    "/{syllabus_id}/outcomes/{co_id}",
    response_model=CourseOutcomeResponse,
)
async def update_outcome(
    syllabus_id: UUID,
    co_id: UUID,
    payload: CourseOutcomeUpdate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseOutcomeResponse:
    try:
        co = await SyllabusService.update_co(co_id, syllabus_id, payload, db=db)
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_CO_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="CourseOutcome",
        target_id=str(co_id),
        metadata={"syllabus_id": str(syllabus_id), "changes": payload.model_dump(exclude_none=True)},
    )
    return CourseOutcomeResponse.model_validate(co)


@router.delete("/{syllabus_id}/outcomes/{co_id}", status_code=200)
async def delete_outcome(
    syllabus_id: UUID,
    co_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await SyllabusService.delete_co(co_id, syllabus_id, db=db)
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_CO_DELETED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="CourseOutcome",
        target_id=str(co_id),
        metadata={"syllabus_id": str(syllabus_id), "co_id": str(co_id)},
    )
    return {"status": "deleted"}


# ===========================================================================
# CO-PO Mappings
# ===========================================================================

@router.put(
    "/{syllabus_id}/outcomes/{co_id}/mappings",
    response_model=list[COPOMappingResponse],
)
async def update_copo_mappings(
    syllabus_id: UUID,
    co_id: UUID,
    payload: COPOMappingBulkUpdate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[COPOMappingResponse]:
    try:
        mappings = await SyllabusService.update_copo_mappings(co_id, syllabus_id, payload, db=db)
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_COPO_MAPPING_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="COPOMapping",
        target_id=str(co_id),
        metadata={
            "syllabus_id":    str(syllabus_id),
            "co_id":          str(co_id),
            "mappings_count": len(mappings),
        },
    )
    return [COPOMappingResponse.model_validate(m) for m in mappings]


@router.get("/{syllabus_id}/copo-matrix", response_model=COPOMatrixResponse)
async def get_copo_matrix(
    syllabus_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> COPOMatrixResponse:
    matrix = await SyllabusService.build_copo_matrix(syllabus_id, db=db)
    if matrix is None:
        raise _404()
    return matrix


# ===========================================================================
# Units
# ===========================================================================

@router.get("/{syllabus_id}/units", response_model=list[SyllabusUnitResponse])
async def list_units(
    syllabus_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[SyllabusUnitResponse]:
    units = await SyllabusService.list_units(syllabus_id, db=db)
    return [SyllabusUnitResponse.model_validate(u) for u in units]


@router.post("/{syllabus_id}/units", response_model=SyllabusUnitResponse, status_code=201)
async def add_unit(
    syllabus_id: UUID,
    payload: SyllabusUnitCreate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusUnitResponse:
    try:
        unit = await SyllabusService.add_unit(syllabus_id, payload, db=db)
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_UNIT_ADDED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="SyllabusUnit",
        target_id=str(unit.id),
        metadata={"syllabus_id": str(syllabus_id), "unit_number": unit.unit_number},
    )
    return SyllabusUnitResponse.model_validate(unit)


@router.patch("/{syllabus_id}/units/{unit_id}", response_model=SyllabusUnitResponse)
async def update_unit(
    syllabus_id: UUID,
    unit_id: UUID,
    payload: SyllabusUnitUpdate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusUnitResponse:
    try:
        unit = await SyllabusService.update_unit(unit_id, syllabus_id, payload, db=db)
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_UNIT_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="SyllabusUnit",
        target_id=str(unit_id),
        metadata={"syllabus_id": str(syllabus_id), "changes": payload.model_dump(exclude_none=True)},
    )
    return SyllabusUnitResponse.model_validate(unit)


@router.delete("/{syllabus_id}/units/{unit_id}", status_code=200)
async def delete_unit(
    syllabus_id: UUID,
    unit_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await SyllabusService.delete_unit(unit_id, syllabus_id, db=db)
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_UNIT_DELETED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="SyllabusUnit",
        target_id=str(unit_id),
        metadata={"syllabus_id": str(syllabus_id), "unit_id": str(unit_id)},
    )
    return {"status": "deleted"}


@router.put("/{syllabus_id}/units/reorder", status_code=200)
async def reorder_units(
    syllabus_id: UUID,
    payload: SyllabusUnitReorder,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    order_map = {uid: num for uid, num in payload.order}
    try:
        count = await SyllabusService.reorder_units(syllabus_id, order_map, db=db)
    except SyllabusServiceError as e:
        raise _err(e)
    return {"updated": count}


# ===========================================================================
# References — /search must be declared before /{ref_id} to avoid UUID clash
# ===========================================================================

@router.get("/{syllabus_id}/references/search", response_model=list[ReferenceCandidate])
async def search_references(
    syllabus_id: UUID,
    q: str = Query(..., min_length=3, description="Search query"),
    ref_type: RefType = Query(RefType.TEXTBOOK),
    limit: int = Query(5, ge=1, le=20),
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ReferenceCandidate]:
    return await SyllabusService.search_references(q, ref_type=ref_type, limit=limit)


@router.get("/{syllabus_id}/references", response_model=list[SyllabusReferenceResponse])
async def list_references(
    syllabus_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[SyllabusReferenceResponse]:
    refs = await SyllabusService.list_references(syllabus_id, db=db)
    return [SyllabusReferenceResponse.model_validate(r) for r in refs]


@router.post("/{syllabus_id}/references", response_model=SyllabusReferenceResponse, status_code=201)
async def add_reference(
    syllabus_id: UUID,
    payload: SyllabusReferenceCreate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusReferenceResponse:
    try:
        ref = await SyllabusService.add_reference(syllabus_id, payload, db=db)
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_REFERENCE_ADDED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="SyllabusReference",
        target_id=str(ref.id),
        metadata={"syllabus_id": str(syllabus_id), "title": ref.title[:80]},
    )
    return SyllabusReferenceResponse.model_validate(ref)


@router.patch("/{syllabus_id}/references/{ref_id}", response_model=SyllabusReferenceResponse)
async def update_reference(
    syllabus_id: UUID,
    ref_id: UUID,
    payload: SyllabusReferenceUpdate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusReferenceResponse:
    try:
        ref = await SyllabusService.update_reference(ref_id, syllabus_id, payload, db=db)
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_REFERENCE_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="SyllabusReference",
        target_id=str(ref_id),
        metadata={"syllabus_id": str(syllabus_id), "changes": payload.model_dump(exclude_none=True)},
    )
    return SyllabusReferenceResponse.model_validate(ref)


@router.delete("/{syllabus_id}/references/{ref_id}", status_code=200)
async def delete_reference(
    syllabus_id: UUID,
    ref_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await SyllabusService.delete_reference(ref_id, syllabus_id, db=db)
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_REFERENCE_DELETED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="SyllabusReference",
        target_id=str(ref_id),
        metadata={"syllabus_id": str(syllabus_id), "ref_id": str(ref_id)},
    )
    return {"status": "deleted"}


@router.post(
    "/{syllabus_id}/references/{ref_id}/confirm",
    response_model=SyllabusReferenceResponse,
)
async def confirm_reference(
    syllabus_id: UUID,
    ref_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusReferenceResponse:
    try:
        ref = await SyllabusService.confirm_reference(ref_id, syllabus_id, db=db)
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_REFERENCE_CONFIRMED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="SyllabusReference",
        target_id=str(ref_id),
        metadata={"syllabus_id": str(syllabus_id), "ref_id": str(ref_id)},
    )
    return SyllabusReferenceResponse.model_validate(ref)


# ===========================================================================
# Export
# ===========================================================================

@router.post("/{syllabus_id}/export", response_model=SyllabusExportJobResponse, status_code=202)
async def export_syllabus(
    syllabus_id: UUID,
    format: Literal["pdf", "docx", "json"] = Query("pdf", description="Export format"),
    current_user: CurrentUser = Depends(require_roles(*_EXPORT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusExportJobResponse:
    try:
        job_id = await SyllabusService.dispatch_export(
            syllabus_id=syllabus_id,
            export_format=format,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            requested_by_user_id=current_user.user_id,
            db=db,
        )
    except SyllabusServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.SYLLABUS_EXPORT_REQUESTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Syllabus",
        target_id=str(syllabus_id),
        metadata={"job_id": str(job_id), "format": format},
    )
    return SyllabusExportJobResponse(
        job_id=job_id,
        syllabus_id=syllabus_id,
        format=format,
    )
