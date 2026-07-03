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
from app.modules.m01_program_advisor.models import ProgramStatus
from app.modules.m01_program_advisor.repository import (
    CoursePrerequisiteRepository,
    CourseRepository,
    ProgramOutcomeRepository,
)
from app.modules.m01_program_advisor.schemas import (
    ApproveRequest,
    ComplianceResultResponse,
    ComplianceViolationResponse,
    CourseCreate,
    CoursePrerequisiteResponse,
    CourseResponse,
    CourseUpdate,
    GenerateProgramRequest,
    ProgramAIJobResponse,
    ProgramCreate,
    ProgramDetail,
    ProgramExportJobResponse,
    ProgramListResponse,
    ProgramOutcomeCreate,
    ProgramOutcomeResponse,
    ProgramOutcomeUpdate,
    ProgramResponse,
    ProgramStatusResponse,
    ProgramUpdate,
    ProgramVersionResponse,
    RejectRequest,
)
from app.modules.m01_program_advisor.service import ProgramService, ProgramServiceError

router = APIRouter(tags=["programs"])

_WRITE = (TenantRole.ADMIN, TenantRole.DEAN)
_READ  = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)
_DEAN  = (TenantRole.DEAN,)


def _err(e: ProgramServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


# ---------------------------------------------------------------------------
# Program CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=ProgramResponse, status_code=201)
async def create_program(
    payload: ProgramCreate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramResponse:
    try:
        program = await ProgramService.create_program(
            payload, created_by=current_user.user_id, db=db
        )
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.PROGRAM_CREATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Program",
        target_id=str(program.id),
        metadata={
            "title": program.title,
            "degree_type": program.degree_type,
            "department": program.department,
        },
    )
    return ProgramResponse.model_validate(program)


@router.get("", response_model=ProgramListResponse)
async def list_programs(
    status: ProgramStatus | None = Query(None, description="Filter by program status"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramListResponse:
    offset = (page - 1) * page_size
    programs = await ProgramService.list_programs(
        status_filter=status,
        offset=offset,
        limit=page_size,
        caller_role=current_user.role,
        caller_user_id=current_user.user_id,
        db=db,
    )
    total = await ProgramService.count_programs(
        status_filter=status,
        caller_role=current_user.role,
        caller_user_id=current_user.user_id,
        db=db,
    )
    return ProgramListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[ProgramResponse.model_validate(p) for p in programs],
    )


@router.get("/{program_id}", response_model=ProgramDetail)
async def get_program(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramDetail:
    program = await ProgramService.get_program_detail(
        program_id,
        caller_role=current_user.role,
        caller_user_id=current_user.user_id,
        db=db,
    )
    if program is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "message": "Program not found."},
        )
    return ProgramDetail.model_validate(program)


@router.get("/{program_id}/status", response_model=ProgramStatusResponse)
async def get_program_status(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramStatusResponse:
    program = await ProgramService.get_program(
        program_id,
        caller_role=current_user.role,
        caller_user_id=current_user.user_id,
        db=db,
    )
    if program is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "message": "Program not found."},
        )
    return ProgramStatusResponse.model_validate(program)


@router.patch("/{program_id}", response_model=ProgramResponse)
async def update_program(
    program_id: UUID,
    payload: ProgramUpdate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramResponse:
    try:
        program = await ProgramService.update_program(program_id, payload, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.PROGRAM_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Program",
        target_id=str(program_id),
        metadata={"changes": payload.model_dump(exclude_none=True)},
    )
    return ProgramResponse.model_validate(program)


@router.delete("/{program_id}", status_code=200)
async def delete_program(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await ProgramService.delete_program(program_id, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.PROGRAM_DELETED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Program",
        target_id=str(program_id),
        metadata={"program_id": str(program_id)},
    )
    return {"status": "deleted"}


@router.get("/{program_id}/versions", response_model=list[ProgramVersionResponse])
async def list_program_versions(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ProgramVersionResponse]:
    versions = await ProgramService.list_versions(program_id, db=db)
    return [ProgramVersionResponse.model_validate(v) for v in versions]


# ---------------------------------------------------------------------------
# AI generation
# ---------------------------------------------------------------------------

@router.post("/{program_id}/generate", response_model=ProgramAIJobResponse)
@limiter.limit("5/minute")
async def dispatch_ai_generation(
    request: Request,
    program_id: UUID,
    payload: GenerateProgramRequest,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramAIJobResponse:
    try:
        job_id = await ProgramService.dispatch_ai_generation(
            program_id=program_id,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            prompt_hint=payload.prompt_hint,
            ai_instructions=payload.ai_instructions,
            db=db,
        )
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.PROGRAM_GENERATION_QUEUED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Program",
        target_id=str(program_id),
        metadata={"job_id": job_id, "prompt_hint": payload.prompt_hint},
    )
    return ProgramAIJobResponse(job_id=UUID(job_id), program_id=program_id)


@router.get("/{program_id}/jobs/{job_id}")
async def get_job_status(
    program_id: UUID,
    job_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    job = await ProgramService.get_job_status(
        job_id=job_id,
        tenant_id=current_user.tenant_id,
        db=db,
    )
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "message": "Job not found."},
        )
    return job


# ---------------------------------------------------------------------------
# Approval / forking
# ---------------------------------------------------------------------------

@router.post("/{program_id}/approve", response_model=ProgramResponse)
async def approve_program(
    program_id: UUID,
    payload: ApproveRequest,
    current_user: CurrentUser = Depends(require_roles(*_DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramResponse:
    try:
        program = await ProgramService.approve(
            program_id, approved_by=current_user.user_id, db=db
        )
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.PROGRAM_APPROVED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Program",
        target_id=str(program_id),
        metadata={"version": program.version, "ai_model": program.ai_model, "comment": payload.comment},
    )
    return ProgramResponse.model_validate(program)


@router.post("/{program_id}/reject", response_model=ProgramStatusResponse)
async def reject_program(
    program_id: UUID,
    payload: RejectRequest,
    current_user: CurrentUser = Depends(require_roles(*_DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramStatusResponse:
    try:
        program = await ProgramService.reject(program_id, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.PROGRAM_REJECTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Program",
        target_id=str(program_id),
        metadata={"reason": payload.reason},
    )
    return ProgramStatusResponse.model_validate(program)


@router.post("/{program_id}/fork", response_model=ProgramResponse, status_code=201)
async def fork_program(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramResponse:
    try:
        new_program = await ProgramService.fork_program(
            program_id, created_by=current_user.user_id, db=db
        )
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.PROGRAM_FORKED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Program",
        target_id=str(new_program.id),
        metadata={
            "source_id": str(program_id),
            "new_id": str(new_program.id),
            "new_version": new_program.version,
        },
    )
    return ProgramResponse.model_validate(new_program)


# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------

@router.get("/{program_id}/compliance", response_model=ComplianceResultResponse)
async def get_compliance(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ComplianceResultResponse:
    try:
        result = await ProgramService.run_compliance(program_id, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    return ComplianceResultResponse(
        passed=result.passed,
        violations=[
            ComplianceViolationResponse(
                rule_id=v.rule_id,
                rule_ref=v.rule_ref,
                message=v.message,
                severity=v.severity,
            )
            for v in result.violations
        ],
    )


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------

@router.post("/{program_id}/outcomes", response_model=ProgramOutcomeResponse, status_code=201)
async def add_outcome(
    program_id: UUID,
    payload: ProgramOutcomeCreate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramOutcomeResponse:
    try:
        outcome = await ProgramService.add_outcome(program_id, payload, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.PROGRAM_OUTCOME_ADDED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="ProgramOutcome",
        target_id=str(outcome.id),
        metadata={"program_id": str(program_id), "code": outcome.code},
    )
    return ProgramOutcomeResponse.model_validate(outcome)


@router.get("/{program_id}/outcomes", response_model=list[ProgramOutcomeResponse])
async def list_outcomes(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ProgramOutcomeResponse]:
    owned = await ProgramService.get_program(
        program_id, caller_role=current_user.role, caller_user_id=current_user.user_id, db=db
    )
    if owned is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "message": "Program not found."},
        )
    outcomes = await ProgramOutcomeRepository.list_by_program(program_id, db=db)
    return [ProgramOutcomeResponse.model_validate(o) for o in outcomes]


@router.patch("/{program_id}/outcomes/{outcome_id}", response_model=ProgramOutcomeResponse)
async def update_outcome(
    program_id: UUID,
    outcome_id: UUID,
    payload: ProgramOutcomeUpdate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramOutcomeResponse:
    try:
        outcome = await ProgramService.update_outcome(outcome_id, program_id, payload, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.PROGRAM_OUTCOME_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="ProgramOutcome",
        target_id=str(outcome_id),
        metadata={"program_id": str(program_id), "changes": payload.model_dump(exclude_none=True)},
    )
    return ProgramOutcomeResponse.model_validate(outcome)


@router.delete("/{program_id}/outcomes/{outcome_id}", status_code=200)
async def delete_outcome(
    program_id: UUID,
    outcome_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await ProgramService.delete_outcome(outcome_id, program_id, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.PROGRAM_OUTCOME_DELETED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="ProgramOutcome",
        target_id=str(outcome_id),
        metadata={"program_id": str(program_id), "outcome_id": str(outcome_id)},
    )
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

@router.post("/{program_id}/courses", response_model=CourseResponse, status_code=201)
async def add_course(
    program_id: UUID,
    payload: CourseCreate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseResponse:
    try:
        course = await ProgramService.add_course(program_id, payload, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.PROGRAM_COURSE_ADDED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Course",
        target_id=str(course.id),
        metadata={
            "program_id": str(program_id),
            "code": course.code,
            "credits": course.credits,
            "semester": course.semester,
        },
    )
    return CourseResponse.model_validate(course)


@router.get("/{program_id}/courses", response_model=list[CourseResponse])
async def list_courses(
    program_id: UUID,
    semester: int | None = Query(None, ge=1, description="Filter by semester number"),
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[CourseResponse]:
    owned = await ProgramService.get_program(
        program_id, caller_role=current_user.role, caller_user_id=current_user.user_id, db=db
    )
    if owned is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "message": "Program not found."},
        )
    if semester is not None:
        courses = await CourseRepository.list_by_semester(program_id, semester, db=db)
    else:
        courses = await CourseRepository.list_by_program(program_id, db=db)
    return [CourseResponse.model_validate(c) for c in courses]


@router.patch("/{program_id}/courses/{course_id}", response_model=CourseResponse)
async def update_course(
    program_id: UUID,
    course_id: UUID,
    payload: CourseUpdate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseResponse:
    try:
        course = await ProgramService.update_course(course_id, program_id, payload, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.PROGRAM_COURSE_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Course",
        target_id=str(course_id),
        metadata={"program_id": str(program_id), "changes": payload.model_dump(exclude_none=True)},
    )
    return CourseResponse.model_validate(course)


@router.delete("/{program_id}/courses/{course_id}", status_code=200)
async def delete_course(
    program_id: UUID,
    course_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await ProgramService.delete_course(course_id, program_id, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.PROGRAM_COURSE_DELETED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Course",
        target_id=str(course_id),
        metadata={"program_id": str(program_id), "course_id": str(course_id)},
    )
    return {"status": "deleted"}


@router.get(
    "/{program_id}/courses/{course_id}/prerequisites",
    response_model=list[CoursePrerequisiteResponse],
)
async def list_prerequisites(
    program_id: UUID,
    course_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[CoursePrerequisiteResponse]:
    prereqs = await CoursePrerequisiteRepository.list_by_course(course_id, db=db)
    return [CoursePrerequisiteResponse.model_validate(p) for p in prereqs]


# ---------------------------------------------------------------------------
# Export  (#23)
# ---------------------------------------------------------------------------

@router.post("/{program_id}/export", response_model=ProgramExportJobResponse, status_code=202)
async def export_program(
    program_id: UUID,
    format: Literal["pdf", "docx"] = Query("pdf", description="Export format: pdf or docx"),
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramExportJobResponse:
    try:
        job_id = await ProgramService.dispatch_export(
            program_id=program_id,
            export_format=format,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            requested_by_user_id=current_user.user_id,
            db=db,
        )
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.PROGRAM_EXPORT_REQUESTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Program",
        target_id=str(program_id),
        metadata={"job_id": str(job_id), "format": format},
    )
    return ProgramExportJobResponse(
        job_id=job_id,
        program_id=program_id,
        format=format,
    )
