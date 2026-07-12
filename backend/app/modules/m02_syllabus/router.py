"""
M02 Syllabus router — the OFFICIAL university syllabus. RBAC enforced.

Who may do what
---------------
The syllabus is CURRICULUM, and the curriculum belongs to the Board. That is the
whole point of Phase A:

  Before: Faculty AUTHORED the syllabus; the Dean reviewed, approved and locked it.
  Now:    the Board (Board / University Members) generates, edits and approves it;
          it is locked with the curriculum. Faculty TEACH to the approved syllabus
          and build lesson plans, PPTs, course kits, assignments and question
          papers under it — they never write it. The Dean reads it.

  _WRITE  — create, edit, AI-generate, approve, delete   (Board + ADMIN)
  _READ   — view                                          (every content role)
  _EXPORT — export an approved official syllabus          (same as _READ)

_WRITE goes through `require_responsibility`, so a senior professor who sits on
the Board (a FACULTY account holding a BOARD grant) exercises Board rights from
their single account — exactly as real universities staff a Board of Studies.

Removed with the old workflow: submit-for-review, resubmit, reject,
request-revision, dean-overview, lock and unlock. The first four only made sense
when the author and the approver were different people. Lock/unlock is gone
because a syllabus is locked by CURRICULUM APPROVAL (governance.approve_and_lock)
— the structure and the syllabus freeze together — and is never unlocked.

All business logic lives in SyllabusService.
Router is pure HTTP glue: deserialise -> call service -> audit -> serialise.
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
from app.core.auth.dependencies import get_tenant_db_dep, require_roles, require_responsibility
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.rate_limiting import limiter
from app.modules.m02_syllabus.schemas import (
    ApproveRequest,
    COPOMappingBulkUpdate,
    COPOMappingResponse,
    COPOMatrixResponse,
    ComplianceCheckResponse,
    CourseInformation,
    CourseOutcomeCreate,
    CourseOutcomeResponse,
    CourseOutcomeUpdate,
    DeanDocumentEditRequest,
    ForkRequest,
    GenerateSyllabusRequest,
    ReferenceCandidate,
    RegenerateSectionRequest,
    SyllabusAIJobResponse,
    SyllabusCreate,
    SyllabusDetail,
    SyllabusExportJobResponse,
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
from app.modules.m02_syllabus.formatting import course_information
from app.modules.m02_syllabus.models import RefType, SyllabusStatus
from app.modules.m02_syllabus.service import SyllabusService, SyllabusServiceError

router = APIRouter(tags=["syllabi"])

_WRITE  = (TenantRole.ADMIN, TenantRole.BOARD)
_READ   = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY, TenantRole.BOARD)
_EXPORT = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY, TenantRole.BOARD)

# The Dean's post-approval edit of a guideline document — Internship, Mini Project,
# Major Project and Seminar only. The service refuses a theory syllabus outright
# (SyllabusService.dean_edit_document); this gate is only about WHO may ask.
_DEAN_EDIT = (TenantRole.ADMIN, TenantRole.DEAN)


async def _lookup_user(user_id, *, db: AsyncSession) -> dict:
    """Return {email, full_name} for a user_id or empty dict if not found."""
    from sqlalchemy import text as _text
    result = await db.execute(
        _text("SELECT email, full_name FROM users WHERE id = :uid"),
        {"uid": str(user_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else {}


async def _program_id_for_syllabus(syllabus_id: UUID, db: AsyncSession) -> str | None:
    """The curriculum this syllabus belongs to, stamped into every audit entry.

    The Dean is shown a summary of everything the Board changed while it held
    their curriculum (governance.get_change_summary), and that summary is built by
    querying the audit log for events on the program. But an audit row for a
    syllabus edit carries the SYLLABUS id, not the program id — so without this
    stamp the Board's syllabus work would be invisible to the query, and the Dean
    would be told the Board had changed nothing.
    """
    from sqlalchemy import text as _text
    return (
        await db.execute(
            _text(
                "SELECT c.program_id::text FROM syllabi s "
                "JOIN courses c ON c.id = s.course_id WHERE s.id = :sid"
            ),
            {"sid": str(syllabus_id)},
        )
    ).scalar_one_or_none()


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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
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


@router.get("/{syllabus_id}", response_model=SyllabusDetail)
async def get_syllabus(
    syllabus_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusDetail:
    from sqlalchemy import select
    from app.modules.m01_program_advisor.models import Course, Program
    from app.modules.m_academics.dean_scope import get_dean_program_ids

    syllabus = await SyllabusService.get_syllabus_detail(syllabus_id, db=db)
    if syllabus is None:
        raise _404()

    # A faculty may only open a syllabus for a course they teach — otherwise a
    # colleague's syllabus is one guessable id away. Mirrors the ownership the
    # LIST endpoint already enforces (m02/service.py list_syllabi FACULTY branch).
    if current_user.role == "FACULTY":
        from app.modules.m_academics.faculty_scope import faculty_teaches_course
        if not await faculty_teaches_course(current_user.user_id, syllabus.course_id, db):
            raise _404()

    detail = SyllabusDetail.model_validate(syllabus)

    course_result = await db.execute(select(Course).where(Course.id == syllabus.course_id))
    course = course_result.scalar_one_or_none()
    if course:
        program_result = await db.execute(select(Program).where(Program.id == course.program_id))
        program = program_result.scalar_one_or_none()
        if current_user.role == "DEAN":
            governed = await get_dean_program_ids(current_user.user_id, current_user.role, db)
            owned_acad_id = program.acad_program_id if program else None
            if governed is not None and owned_acad_id not in governed:
                raise _404()
        detail = detail.model_copy(update={
            # The official syllabus header — code, name, credits, L-T-P, contact
            # hours and category — all derived from the course, never stored.
            "course_information": CourseInformation(**course_information(course)),
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusResponse:
    try:
        syllabus = await SyllabusService.update_syllabus(
            syllabus_id, payload,
            caller_role=current_user.role, faculty_user_id=current_user.user_id, db=db,
        )
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
        metadata={
            "changes": payload.model_dump(exclude_none=True),
            "program_id": await _program_id_for_syllabus(syllabus_id, db),
        },
    )
    return SyllabusResponse.model_validate(syllabus)


@router.delete("/{syllabus_id}", status_code=200)
async def delete_syllabus(
    syllabus_id: UUID,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await SyllabusService.delete_syllabus(
            syllabus_id, caller_role=current_user.role,
            faculty_user_id=current_user.user_id, db=db,
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusAIJobResponse:
    # If caller provides updated instructions, persist them first (DRAFT guard in service).
    if payload.custom_instructions is not None:
        try:
            await SyllabusService.update_syllabus(
                syllabus_id,
                SyllabusUpdate(custom_instructions=payload.custom_instructions),
                caller_role=current_user.role, faculty_user_id=current_user.user_id, db=db,
            )
        except SyllabusServiceError as e:
            raise _err(e)
    try:
        job_id = await SyllabusService.dispatch_ai_generation(
            syllabus_id=syllabus_id,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            caller_role=current_user.role,
            faculty_user_id=current_user.user_id,
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


@router.post("/{syllabus_id}/regenerate", response_model=SyllabusAIJobResponse)
@limiter.limit("15/minute")
async def regenerate_section(
    request: Request,
    syllabus_id: UUID,
    payload: RegenerateSectionRequest,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusAIJobResponse:
    """Rewrite ONE section of the syllabus: a unit, the objectives, the outcomes,
    or the bibliography.

    The Board should never have to regenerate a whole syllabus because one unit came
    out weak. By the time they notice, the other four units and the outcomes will
    often have been hand-edited, and a full regeneration throws every bit of that
    away.

    A regenerated unit is told what the OTHER units already teach, so it fills its
    own place in the syllabus rather than drifting into theirs — and it is held to
    exactly the same depth bar as a full generation, so this cannot become the back
    door through which a thin unit reaches the document.
    """
    try:
        job_id = await SyllabusService.dispatch_section_regeneration(
            syllabus_id,
            payload.section.value,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            unit_id=payload.unit_id,
            guidance=payload.guidance,
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
        metadata={
            "job_id":   job_id,
            "section":  payload.section.value,
            "unit_id":  str(payload.unit_id) if payload.unit_id else None,
            "guidance": payload.guidance,
            "program_id": await _program_id_for_syllabus(syllabus_id, db),
        },
    )
    return SyllabusAIJobResponse(job_id=UUID(job_id), syllabus_id=syllabus_id)


@router.patch("/{syllabus_id}/document/dean", response_model=SyllabusResponse)
async def dean_edit_document(
    syllabus_id: UUID,
    payload: DeanDocumentEditRequest,
    current_user: CurrentUser = Depends(require_roles(*_DEAN_EDIT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    """The Dean adapting an APPROVED Internship / Project / Seminar document.

    Permitted because those documents depend on the company, the supervisor and
    institutional policy — things the Board cannot settle at approval time, and the
    Dean must before students start.

    A THEORY syllabus is refused (403). The Board owns the taught curriculum: it
    writes the syllabus and it approves it, and the Dean publishes it without
    rewriting it. The refusal lives in the service, not merely in the UI, because a
    hidden button is a suggestion and this is a rule.

    Unlike every other write, this does NOT withdraw the Board's approval — the
    Board approved the academic substance and the Dean is filling in the
    institutional detail beneath it. The row is stamped instead, so the governance
    trail can always separate the two hands.
    """
    try:
        syllabus = await SyllabusService.dean_edit_document(
            syllabus_id, payload, current_user.user_id, db=db,
        )
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
        metadata={
            "dean_guideline_edit": True,
            "doc_type":   syllabus.doc_type,
            "sections":   sorted((syllabus.document or {}).keys()),
            "note":       payload.note,
            "program_id": await _program_id_for_syllabus(syllabus_id, db),
        },
    )
    return syllabus


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
# State transitions — the Board approves its own syllabus
#
# Gone with the old workflow: submit-for-review, resubmit, reject,
# request-revision, lock and unlock.
#
# The first four existed because Faculty AUTHORED a syllabus and a Dean REVIEWED
# it — two parties, so the work had to be handed between them. The Board writes
# the syllabus and signs it off, so there is nobody to hand it to and nothing to
# send back: when the Board is unhappy with a syllabus, it edits it.
#
# Lock/unlock is gone because locking is not a syllabus-level act any more. A
# syllabus is locked when the CURRICULUM is approved (governance.approve_and_lock)
# — structure and syllabus freeze as one thing, or the pair is incoherent — and
# it is never unlocked. A change means a new curriculum version.
# ===========================================================================

@router.post("/{syllabus_id}/approve", response_model=SyllabusStatusResponse)
async def approve_syllabus(
    syllabus_id: UUID,
    payload: ApproveRequest,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusStatusResponse:
    """DRAFT -> APPROVED. The Board signs off one official syllabus.

    This is a per-subject sign-off, not the curriculum decision. The curriculum
    can only be approved once EVERY subject has passed through here — see
    governance.approve_and_lock.
    """
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
        metadata={
            "version": syllabus.version,
            "comment": payload.comment,
            "program_id": str(await _program_id_for_syllabus(syllabus_id, db)),
        },
    )
    return SyllabusStatusResponse.model_validate(syllabus)


@router.post("/{syllabus_id}/fork", response_model=SyllabusStatusResponse, status_code=201)
async def fork_syllabus(
    syllabus_id: UUID,
    payload: ForkRequest,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SyllabusStatusResponse:
    """Fork a syllabus version into a new DRAFT. Board only."""
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
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
        metadata={
            "syllabus_id": str(syllabus_id),
            "code": co.code,
            "program_id": await _program_id_for_syllabus(syllabus_id, db),
        },
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
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
        metadata={
            "syllabus_id": str(syllabus_id),
            "changes": payload.model_dump(exclude_none=True),
            "program_id": await _program_id_for_syllabus(syllabus_id, db),
        },
    )
    return CourseOutcomeResponse.model_validate(co)


@router.delete("/{syllabus_id}/outcomes/{co_id}", status_code=200)
async def delete_outcome(
    syllabus_id: UUID,
    co_id: UUID,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
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
        metadata={
            "syllabus_id": str(syllabus_id),
            "co_id": str(co_id),
            "program_id": await _program_id_for_syllabus(syllabus_id, db),
        },
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
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
        metadata={
            "syllabus_id": str(syllabus_id),
            "unit_number": unit.unit_number,
            "program_id": await _program_id_for_syllabus(syllabus_id, db),
        },
    )
    return SyllabusUnitResponse.model_validate(unit)


@router.patch("/{syllabus_id}/units/{unit_id}", response_model=SyllabusUnitResponse)
async def update_unit(
    syllabus_id: UUID,
    unit_id: UUID,
    payload: SyllabusUnitUpdate,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
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
        metadata={
            "syllabus_id": str(syllabus_id),
            "changes": payload.model_dump(exclude_none=True),
            "program_id": await _program_id_for_syllabus(syllabus_id, db),
        },
    )
    return SyllabusUnitResponse.model_validate(unit)


@router.delete("/{syllabus_id}/units/{unit_id}", status_code=200)
async def delete_unit(
    syllabus_id: UUID,
    unit_id: UUID,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
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
        metadata={
            "syllabus_id": str(syllabus_id),
            "unit_id": str(unit_id),
            "program_id": await _program_id_for_syllabus(syllabus_id, db),
        },
    )
    return {"status": "deleted"}


@router.put("/{syllabus_id}/units/reorder", status_code=200)
async def reorder_units(
    syllabus_id: UUID,
    payload: SyllabusUnitReorder,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
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
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
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
        metadata={
            "syllabus_id": str(syllabus_id),
            "title": ref.title[:80],
            "program_id": await _program_id_for_syllabus(syllabus_id, db),
        },
    )
    return SyllabusReferenceResponse.model_validate(ref)


@router.patch("/{syllabus_id}/references/{ref_id}", response_model=SyllabusReferenceResponse)
async def update_reference(
    syllabus_id: UUID,
    ref_id: UUID,
    payload: SyllabusReferenceUpdate,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
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
        metadata={
            "syllabus_id": str(syllabus_id),
            "changes": payload.model_dump(exclude_none=True),
            "program_id": await _program_id_for_syllabus(syllabus_id, db),
        },
    )
    return SyllabusReferenceResponse.model_validate(ref)


@router.delete("/{syllabus_id}/references/{ref_id}", status_code=200)
async def delete_reference(
    syllabus_id: UUID,
    ref_id: UUID,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
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
        metadata={
            "syllabus_id": str(syllabus_id),
            "ref_id": str(ref_id),
            "program_id": await _program_id_for_syllabus(syllabus_id, db),
        },
    )
    return {"status": "deleted"}


@router.post(
    "/{syllabus_id}/references/{ref_id}/confirm",
    response_model=SyllabusReferenceResponse,
)
async def confirm_reference(
    syllabus_id: UUID,
    ref_id: UUID,
    current_user: CurrentUser = Depends(require_responsibility(*_WRITE)),
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
