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

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

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
    SyllabusAIJobResponse,
    SyllabusCreate,
    SyllabusDetail,
    SyllabusExportJobResponse,
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
# RBAC role sets (M02-specific — FACULTY can write; DEAN can only lock/view)
# ---------------------------------------------------------------------------
_WRITE  = (TenantRole.ADMIN, TenantRole.FACULTY)
_READ   = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)
_LOCK   = (TenantRole.ADMIN, TenantRole.DEAN)
_EXPORT = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)


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
            payload, created_by=current_user.user_id, db=db
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
    course_id: UUID = Query(..., description="Course ID (required)"),
    status: SyllabusStatus | None = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusListResponse:
    total, items = await SyllabusService.list_syllabi(
        course_id=course_id,
        status_filter=status,
        page=page,
        page_size=page_size,
        db=db,
    )
    return SyllabusListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[SyllabusResponse.model_validate(s) for s in items],
    )


@router.get("/{syllabus_id}", response_model=SyllabusDetail)
async def get_syllabus(
    syllabus_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusDetail:
    syllabus = await SyllabusService.get_syllabus_detail(syllabus_id, db=db)
    if syllabus is None:
        raise _404()
    return SyllabusDetail.model_validate(syllabus)


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
        await SyllabusService.delete_syllabus(syllabus_id, db=db)
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

@router.post("/{syllabus_id}/approve", response_model=SyllabusStatusResponse)
async def approve_syllabus(
    syllabus_id: UUID,
    payload: ApproveRequest,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusStatusResponse:
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
        metadata={"version": syllabus.version, "comment": payload.comment},
    )
    return SyllabusStatusResponse.model_validate(syllabus)


@router.post("/{syllabus_id}/reject", response_model=SyllabusStatusResponse, status_code=201)
async def reject_syllabus(
    syllabus_id: UUID,
    payload: RejectRequest,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusStatusResponse:
    try:
        new_syllabus = await SyllabusService.reject(
            syllabus_id,
            reason=payload.reason,
            forked_by=current_user.user_id,
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
        metadata={
            "reason":          payload.reason,
            "new_syllabus_id": str(new_syllabus.id),
            "new_version":     new_syllabus.version,
        },
    )
    return SyllabusStatusResponse.model_validate(new_syllabus)


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
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
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
