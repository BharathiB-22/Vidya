from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.dependencies import get_current_user, get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.governance.service import (
    GovernanceServiceError,
    acts_as_governance,
    get_governance_info,
    get_submission_checklist,
    submit_for_approval,
)
from app.core.rate_limiting import limiter
from app.modules.m01_program_advisor.models import ProgramStatus
from app.modules.m01_program_advisor.repository import (
    CoursePrerequisiteRepository,
    CourseRepository,
    ProgramOutcomeRepository,
    ProgramRepository,
)
from app.modules.m01_program_advisor.service import (
    EDITABLE_STATUSES,
    GOVERNANCE_EDIT_STATUSES,
)
from app.core.governance.schemas import SubmissionChecklist, SubmitForApprovalRequest
from app.modules.m01_program_advisor.schemas import (
    ComplianceResultResponse,
    ComplianceViolationResponse,
    CourseCreate,
    CoursePrerequisiteResponse,
    CourseResponse,
    CourseUpdate,
    ElectiveBasketCreate,
    ElectiveBasketResponse,
    ElectiveBasketUpdate,
    ElectiveChoiceCreate,
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
    PublishRequest,
)
from app.modules.m01_program_advisor.service import ProgramService, ProgramServiceError  # noqa: E402

logger = logging.getLogger("vidya.router.m01")

router = APIRouter(tags=["programs"])

# Phase A — Academic Governance V1.
#
#   _DEAN_OWNED  acts only the Dean performs on a curriculum they still hold:
#                create it, delete it, run AI structure generation, fork a new
#                version. Admin is included as the tenant's break-glass role.
#   _READ        who may look at a curriculum. The governance authority reads
#                every one of them — that is the whole point of the review queue.
#   _DEAN        publish. The Dean releases what governance has locked.
#
# Structural EDITS (courses, credits, hours, outcomes, elective baskets) are not
# a fixed role list: they depend on who owns the curriculum *right now*. That is
# `assert_can_edit_structure` below.
_DEAN_OWNED = (TenantRole.ADMIN, TenantRole.DEAN)
_READ       = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY, TenantRole.BOARD)
_DEAN       = (TenantRole.DEAN,)


def _err(e: ProgramServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


def _gov_err(e: GovernanceServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


async def assert_can_edit_structure(
    program_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CurrentUser:
    """Gate every structural edit on WHO owns the curriculum in its current state.

        DRAFT / GENERATION_FAILED   → the Dean (and Admin)
        PENDING_APPROVAL            → the Board (and Admin). The Dean is read-only,
                                      permanently — submitting is a one-way handover,
                                      and there is no path back.
        APPROVED / PUBLISHED        → nobody. Locked forever. Create a new version.

    The Board's window stays open for the WHOLE of PENDING_APPROVAL — there is no
    mid-flight structure freeze. The Board may keep revising right up to the
    moment it approves. What stops a syllabus going stale underneath such an edit
    is not a lock but `invalidate_syllabus_for_course` below, feeding the approve
    gate.

    This runs on the API, not just in the UI, so a hand-rolled request cannot get
    around it.
    """
    program = await ProgramRepository.get_by_id(program_id, db=db)
    if program is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "message": "Program not found."},
        )

    if program.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "CURRICULUM_LOCKED",
                "message": (
                    f"This curriculum is {program.status.value} and is locked "
                    "permanently. Nobody may edit it — not the Dean, not the "
                    "Board, not an Admin. Create a new curriculum version to make "
                    "academic changes."
                ),
            },
        )

    if current_user.is_super_admin or current_user.viewing_role == TenantRole.ADMIN.value:
        return current_user

    is_governance = await acts_as_governance(current_user, db)

    if program.status in GOVERNANCE_EDIT_STATUSES:
        if not is_governance:
            info = await get_governance_info(current_user.tenant_id, db)
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "AWAITING_GOVERNANCE",
                    "message": (
                        f"This curriculum has been submitted and is now owned by the "
                        f"{info.body_label}, which will review it, enhance it where "
                        "the academics require, and finalize it. You will be notified "
                        "when it is ready to publish."
                    ),
                },
            )
        return current_user

    # DRAFT / GENERATION_FAILED — the Dean's window.
    if current_user.viewing_role == TenantRole.DEAN.value:
        return current_user

    raise HTTPException(
        status_code=403,
        detail={
            "error": "FORBIDDEN",
            "message": "Only the Dean may edit a curriculum that has not been submitted.",
        },
    )


async def invalidate_syllabus_for_course(course_id: UUID, db: AsyncSession) -> None:
    """A structural edit to a course un-approves its official syllabus.

    Credits, L-T-P, code, title and semester all print in the syllabus header, and
    the unit hours are paced against the contact hours derived from L-T-P. Change
    any of them and the Board's earlier sign-off no longer describes the document
    it signed off on — so the syllabus goes back to DRAFT and must be looked at
    again.

    This is the mechanism that lets the Board edit structure freely for the whole
    review, with no freeze anywhere: a stale syllabus is pushed straight back into
    its queue, and the approve gate (which demands EVERY subject be APPROVED)
    cannot pass until someone has re-read it. The invariant is held by the gate,
    not by a lock.

    Deliberately does not commit — this must land in the same transaction as the
    edit that caused it, or a crash in between would leave an approved syllabus
    describing a course that had already moved.
    """
    from app.modules.m02_syllabus.service import SyllabusService

    await SyllabusService.invalidate_for_course(course_id, db=db)


# ---------------------------------------------------------------------------
# Program CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=ProgramResponse, status_code=201)
async def create_program(
    payload: ProgramCreate,
    current_user: CurrentUser = Depends(require_roles(*_DEAN_OWNED)),
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
        caller_role=current_user.viewing_role,
        caller_user_id=current_user.user_id,
        db=db,
    )
    total = await ProgramService.count_programs(
        status_filter=status,
        caller_role=current_user.viewing_role,
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
        caller_role=current_user.viewing_role,
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
        caller_role=current_user.viewing_role,
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
    current_user: CurrentUser = Depends(assert_can_edit_structure),
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
        # program_id is stamped even though target_id already carries it: the
        # Dean's change summary reads metadata->>'program_id' uniformly across
        # every entity type (course, basket, outcome, syllabus), and a Program
        # row that only set target_id would be the one thing the query missed.
        metadata={
            "program_id": str(program_id),
            "changes": payload.model_dump(exclude_none=True),
        },
    )
    return ProgramResponse.model_validate(program)


@router.delete("/{program_id}", status_code=200)
async def delete_program(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_DEAN_OWNED)),
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
    current_user: CurrentUser = Depends(require_roles(*_DEAN_OWNED)),
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
# Submission / publication / forking
#
# The Dean's two acts on the approval path. Approving and locking belong to the
# governance authority and live in /governance (core/governance/router.py) —
# there is deliberately no Dean-facing approve endpoint any more.
# ---------------------------------------------------------------------------

@router.post("/{program_id}/submit", response_model=ProgramStatusResponse)
async def submit_program_for_approval(
    program_id: UUID,
    payload: SubmitForApprovalRequest,
    current_user: CurrentUser = Depends(require_roles(*_DEAN_OWNED)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramStatusResponse:
    """DRAFT -> PENDING_APPROVAL. A one-way handover.

    The Dean hands the academic plan to the Board. From this moment the Dean is
    read-only on this curriculum version — permanently. There is no return path:
    the Board will enhance whatever needs enhancing itself, write the official
    syllabus, approve and lock. The Dean's next and only act is to publish.

    Requires the Academic Year and Batch to be set, and the curriculum to pass
    compliance.
    """
    try:
        await submit_for_approval(
            program_id, submitted_by=current_user.user_id, note=payload.note, db=db,
        )
    except GovernanceServiceError as e:
        raise _gov_err(e)

    program = await ProgramService.get_program(program_id, db=db)
    await AuditService.log(
        AuditEventType.CURRICULUM_SUBMITTED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Program",
        target_id=str(program_id),
        metadata={
            "program_id": str(program_id),
            "version": program.version,
            "note": payload.note,
        },
    )
    await _notify_submission(program, current_user, db)
    return ProgramStatusResponse.model_validate(program)


@router.get("/{program_id}/submission-check", response_model=SubmissionChecklist)
async def submission_check(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_DEAN_OWNED)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SubmissionChecklist:
    """What the Dean still has to finish before the curriculum can be submitted.

    Submitting is irreversible — the Dean hands the curriculum over and never gets
    it back — so the UI shows this as a checklist BEFORE the act rather than as an
    error afterwards. Each failing line names the section that fixes it.

    Read-only, and it does NOT replace the guard in `submit_for_approval`: the API
    refuses a bad submission regardless of whether anyone called this first.
    """
    try:
        return await get_submission_checklist(program_id, db)
    except GovernanceServiceError as e:
        raise _gov_err(e)


async def _notify_submission(program, actor: CurrentUser, db: AsyncSession) -> None:
    """Tell the Board there is work waiting, and confirm to the Dean that the
    curriculum has entered review.

    Best-effort: the submit has already committed, and a notification failure must
    not make a successful handover look like it failed.
    """
    from sqlalchemy import text as _text

    from app.core.notifications.models import NotificationType
    from app.core.notifications.service import NotificationService

    try:
        info = await get_governance_info(actor.tenant_id, db)

        # Every Board member: a base BOARD role, or an active BOARD grant (a
        # senior professor sitting on the Board keeps one account). A Dean is
        # excluded even with a grant — they can never act as governance.
        members = (
            await db.execute(
                _text(
                    "SELECT DISTINCT u.id, u.email FROM users u "
                    "LEFT JOIN faculty_role_grants g "
                    "  ON g.faculty_user_id = u.id AND g.role_code = 'BOARD' AND g.is_active = true "
                    "WHERE u.is_active = true AND u.role <> 'DEAN' "
                    "  AND (u.role = 'BOARD' OR g.id IS NOT NULL)"
                )
            )
        ).mappings().all()

        for member in members:
            await NotificationService.send(
                NotificationType.CURRICULUM_SUBMITTED,
                recipient_user_id=member["id"],
                recipient_email=member["email"],
                title=f"New curriculum for {info.body_label} review",
                body=(
                    f"{program.title} (version {program.version}) has been submitted by the Dean "
                    f"and is now owned by the {info.body_label}. Review it, enhance it where the "
                    "academics require, generate the official syllabus, and approve it."
                ),
                entity_type="Program",
                entity_id=str(program.id),
                db=db,
            )

        await NotificationService.send(
            NotificationType.CURRICULUM_SUBMITTED,
            recipient_user_id=actor.user_id,
            recipient_email=actor.email,
            title=f"Curriculum submitted to the {info.body_label}",
            body=(
                f"{program.title} (version {program.version}) has entered {info.body_label} review. "
                "It is now read-only for you. You will be notified when it is finalized, and can "
                "then publish it."
            ),
            entity_type="Program",
            entity_id=str(program.id),
            db=db,
        )
    except Exception:
        logger.warning(
            "m01.submit: notification failed (non-blocking) program=%s", program.id, exc_info=True,
        )


@router.post("/{program_id}/publish", response_model=ProgramResponse)
async def publish_program(
    program_id: UUID,
    payload: PublishRequest,
    current_user: CurrentUser = Depends(require_roles(*_DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ProgramResponse:
    try:
        program = await ProgramService.publish(
            program_id, published_by=current_user.user_id, db=db
        )
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.PROGRAM_PUBLISHED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Program",
        target_id=str(program_id),
        metadata={
            "program_id": str(program_id),
            "version": program.version,
            "comment": payload.comment,
        },
    )
    return ProgramResponse.model_validate(program)


# There is no reject endpoint, and no return endpoint. The Board is the academic
# authority: when it disagrees with the Dean's plan it enhances the plan itself.
# Work never comes back to the Dean for correction. The only way to change an
# approved curriculum is to create a new version.


@router.post("/{program_id}/fork", response_model=ProgramResponse, status_code=201)
async def fork_program(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_DEAN_OWNED)),
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
    current_user: CurrentUser = Depends(assert_can_edit_structure),
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
        program_id, caller_role=current_user.viewing_role, caller_user_id=current_user.user_id, db=db
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
    current_user: CurrentUser = Depends(assert_can_edit_structure),
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
    current_user: CurrentUser = Depends(assert_can_edit_structure),
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
    current_user: CurrentUser = Depends(assert_can_edit_structure),
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
        program_id, caller_role=current_user.viewing_role, caller_user_id=current_user.user_id, db=db
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
    current_user: CurrentUser = Depends(assert_can_edit_structure),
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
    current_user: CurrentUser = Depends(assert_can_edit_structure),
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
# Elective Baskets — a named group of elective courses within one program+
# semester. Electives are never a single standalone course; Dean/Faculty add
# any number of elective courses into a basket while the Program is still
# editable (Draft/Pending Approval), and it becomes visible to student
# registration once the Program is Published (see m_academics electives).
# ---------------------------------------------------------------------------

@router.post("/{program_id}/electives/baskets", response_model=ElectiveBasketResponse, status_code=201)
async def add_basket(
    program_id: UUID,
    payload: ElectiveBasketCreate,
    current_user: CurrentUser = Depends(assert_can_edit_structure),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveBasketResponse:
    try:
        basket = await ProgramService.add_basket(program_id, payload, current_user.user_id, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.ELECTIVE_BASKET_CREATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="ElectiveBasket",
        target_id=str(basket.id),
        metadata={"program_id": str(program_id), "name": basket.name, "semester": basket.semester},
    )
    return ElectiveBasketResponse.model_validate(basket)


@router.get("/{program_id}/electives/baskets", response_model=list[ElectiveBasketResponse])
async def list_baskets(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ElectiveBasketResponse]:
    baskets = await ProgramService.list_baskets(program_id, db=db)
    return [ElectiveBasketResponse.model_validate(b) for b in baskets]


@router.patch("/{program_id}/electives/baskets/{basket_id}", response_model=ElectiveBasketResponse)
async def update_basket(
    program_id: UUID,
    basket_id: UUID,
    payload: ElectiveBasketUpdate,
    current_user: CurrentUser = Depends(assert_can_edit_structure),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveBasketResponse:
    try:
        basket = await ProgramService.update_basket(basket_id, program_id, payload, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.ELECTIVE_BASKET_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="ElectiveBasket",
        target_id=str(basket_id),
        metadata={"program_id": str(program_id), "changes": payload.model_dump(exclude_none=True)},
    )
    return ElectiveBasketResponse.model_validate(basket)


@router.delete("/{program_id}/electives/baskets/{basket_id}", status_code=200)
async def delete_basket(
    program_id: UUID,
    basket_id: UUID,
    current_user: CurrentUser = Depends(assert_can_edit_structure),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await ProgramService.delete_basket(basket_id, program_id, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.ELECTIVE_BASKET_DELETED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="ElectiveBasket",
        target_id=str(basket_id),
        metadata={"program_id": str(program_id)},
    )
    return {"status": "deleted"}


@router.delete("/{program_id}/courses/{course_id}/basket", response_model=CourseResponse)
async def remove_course_from_basket(
    program_id: UUID,
    course_id: UUID,
    current_user: CurrentUser = Depends(assert_can_edit_structure),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseResponse:
    try:
        course = await ProgramService.remove_course_from_basket(course_id, program_id, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    return CourseResponse.model_validate(course)


# ---------------------------------------------------------------------------
# Elective slot choices + lifecycle.
#
# Gated on the SLOT's status, not the program's: a Dean must be able to fill in
# what Elective 1 offers this year on a curriculum published long ago. The
# course code is generated server-side — the Dean never types one.
# ---------------------------------------------------------------------------

@router.post(
    "/{program_id}/electives/baskets/{basket_id}/choices",
    response_model=CourseResponse, status_code=201,
)
async def add_elective_choice(
    program_id: UUID,
    basket_id: UUID,
    payload: ElectiveChoiceCreate,
    current_user: CurrentUser = Depends(assert_can_edit_structure),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> CourseResponse:
    try:
        course = await ProgramService.add_choice(program_id, basket_id, payload, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.ELECTIVE_CHOICE_ADDED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Course",
        target_id=str(course.id),
        metadata={
            "program_id": str(program_id), "basket_id": str(basket_id),
            "code": course.code, "title": course.title,
        },
    )
    return CourseResponse.model_validate(course)


@router.delete(
    "/{program_id}/electives/baskets/{basket_id}/choices/{course_id}", status_code=200,
)
async def remove_elective_choice(
    program_id: UUID,
    basket_id: UUID,
    course_id: UUID,
    current_user: CurrentUser = Depends(assert_can_edit_structure),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await ProgramService.remove_choice(program_id, basket_id, course_id, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.ELECTIVE_CHOICE_REMOVED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="Course",
        target_id=str(course_id),
        metadata={"program_id": str(program_id), "basket_id": str(basket_id)},
    )
    return {"status": "deleted"}


@router.post(
    "/{program_id}/electives/baskets/{basket_id}/publish",
    response_model=ElectiveBasketResponse,
)
async def publish_elective_slot(
    program_id: UUID,
    basket_id: UUID,
    current_user: CurrentUser = Depends(assert_can_edit_structure),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveBasketResponse:
    try:
        slot = await ProgramService.publish_slot(program_id, basket_id, current_user.user_id, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.ELECTIVE_SLOT_PUBLISHED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="ElectiveBasket",
        target_id=str(basket_id),
        metadata={"program_id": str(program_id), "name": slot.name},
    )
    return ElectiveBasketResponse.model_validate(slot)


@router.post(
    "/{program_id}/electives/baskets/{basket_id}/open-registration",
    response_model=ElectiveBasketResponse,
)
async def open_elective_registration(
    program_id: UUID,
    basket_id: UUID,
    current_user: CurrentUser = Depends(assert_can_edit_structure),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveBasketResponse:
    try:
        slot = await ProgramService.open_slot_registration(program_id, basket_id, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.ELECTIVE_SLOT_REG_OPENED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="ElectiveBasket",
        target_id=str(basket_id),
        metadata={"program_id": str(program_id), "name": slot.name},
    )
    return ElectiveBasketResponse.model_validate(slot)


@router.post(
    "/{program_id}/electives/baskets/{basket_id}/close-registration",
    response_model=ElectiveBasketResponse,
)
async def close_elective_registration(
    program_id: UUID,
    basket_id: UUID,
    current_user: CurrentUser = Depends(assert_can_edit_structure),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveBasketResponse:
    try:
        slot = await ProgramService.close_slot_registration(program_id, basket_id, db=db)
    except ProgramServiceError as e:
        raise _err(e)
    await AuditService.log(
        AuditEventType.ELECTIVE_SLOT_REG_CLOSED,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
        target_entity="ElectiveBasket",
        target_id=str(basket_id),
        metadata={"program_id": str(program_id), "name": slot.name},
    )
    return ElectiveBasketResponse.model_validate(slot)


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
