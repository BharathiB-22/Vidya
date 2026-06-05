"""
SIS Hall Ticket Eligibility — H58 Router.

RBAC:
  _MANAGERS  = ADMIN, DEAN   (compute, publish, override, generate batch, view all)
  _FACULTY   = FACULTY only  (advisory view — own sections)
  _STUDENT   = STUDENT only  (my-eligibility, my hall ticket)
  _ALL_READ  = ADMIN, DEAN, FACULTY (dashboard and single-row reads)
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.hallticket_schemas import (
    EligibilityComputeIn, EligibilityComputeResult,
    EligibilityDashboardOut, EligibilityOut, EligibilityOverrideIn,
    EligibilityPublishIn, EligibilityPublishResult,
    FacultyAdvisoryOut, HallTicketBatchCreateIn, HallTicketBatchOut,
    HallTicketOut, MyEligibilityOut,
)
from app.modules.m11_sis.hallticket_service import HallTicketService, HallTicketServiceError

hallticket_router = APIRouter(prefix="/hall-tickets", tags=["M11 SIS Hall Tickets"])

_MANAGERS = (TenantRole.ADMIN, TenantRole.DEAN)
_FACULTY  = (TenantRole.FACULTY,)
_STUDENT  = (TenantRole.STUDENT,)
_ALL_READ = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)


def _err(e: HallTicketServiceError) -> HTTPException:
    return HTTPException(
        status_code = e.status_code,
        detail      = {"error": e.code, "message": e.message},
    )


# ---------------------------------------------------------------------------
# Compute eligibility (Admin / Dean)
# ---------------------------------------------------------------------------

@hallticket_router.post("/eligibility/compute", response_model=EligibilityComputeResult, status_code=200)
async def compute_eligibility(
    body:         EligibilityComputeIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
) -> EligibilityComputeResult:
    try:
        return await HallTicketService.compute(
            body,
            actor_id    = current_user.user_id,
            actor_role  = current_user.role,
            tenant_id   = current_user.tenant_id,
            schema_name = current_user.schema_name,
            db          = db,
        )
    except HallTicketServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Publish eligibility (Admin / Dean)
# ---------------------------------------------------------------------------

@hallticket_router.post("/eligibility/publish", response_model=EligibilityPublishResult, status_code=200)
async def publish_eligibility(
    body:         EligibilityPublishIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
) -> EligibilityPublishResult:
    try:
        return await HallTicketService.publish(
            body,
            actor_id    = current_user.user_id,
            tenant_id   = current_user.tenant_id,
            schema_name = current_user.schema_name,
            db          = db,
        )
    except HallTicketServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Eligibility dashboard (Admin / Dean)
# ---------------------------------------------------------------------------

@hallticket_router.get("/eligibility", response_model=EligibilityDashboardOut)
async def get_eligibility_dashboard(
    semester_id:    UUID          = Query(...),
    section_id:     Optional[UUID] = Query(None),
    status:         Optional[str]  = Query(None),
    publish_status: Optional[str]  = Query(None),
    has_shortage:   Optional[bool] = Query(None),
    current_user:   CurrentUser    = Depends(require_roles(*_MANAGERS)),
    db:             AsyncSession   = Depends(get_tenant_db_dep),
) -> EligibilityDashboardOut:
    try:
        return await HallTicketService.get_dashboard(
            semester_id    = semester_id,
            section_id     = section_id,
            status         = status,
            publish_status = publish_status,
            has_shortage   = has_shortage,
            db             = db,
        )
    except HallTicketServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Single eligibility row (Admin / Dean)
# ---------------------------------------------------------------------------

@hallticket_router.get("/eligibility/{eligibility_id}", response_model=EligibilityOut)
async def get_eligibility(
    eligibility_id: UUID,
    current_user:   CurrentUser  = Depends(require_roles(*_MANAGERS)),
    db:             AsyncSession = Depends(get_tenant_db_dep),
) -> EligibilityOut:
    try:
        return await HallTicketService.get_eligibility(eligibility_id, db)
    except HallTicketServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Override eligibility (Admin / Dean — human gate)
# ---------------------------------------------------------------------------

@hallticket_router.post("/eligibility/{eligibility_id}/override", response_model=EligibilityOut)
async def override_eligibility(
    eligibility_id: UUID,
    body:           EligibilityOverrideIn,
    current_user:   CurrentUser  = Depends(require_roles(*_MANAGERS)),
    db:             AsyncSession = Depends(get_tenant_db_dep),
) -> EligibilityOut:
    try:
        return await HallTicketService.override(
            eligibility_id,
            body,
            actor_id    = current_user.user_id,
            actor_role  = current_user.role,
            tenant_id   = current_user.tenant_id,
            schema_name = current_user.schema_name,
            db          = db,
        )
    except HallTicketServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Faculty advisory view (Faculty — own sections only)
# ---------------------------------------------------------------------------

@hallticket_router.get("/advisory", response_model=FacultyAdvisoryOut)
async def faculty_advisory(
    section_id:   UUID          = Query(...),
    semester_id:  UUID          = Query(...),
    current_user: CurrentUser   = Depends(require_roles(*_FACULTY)),
    db:           AsyncSession  = Depends(get_tenant_db_dep),
) -> FacultyAdvisoryOut:
    try:
        return await HallTicketService.faculty_advisory(
            section_id  = section_id,
            semester_id = semester_id,
            faculty_id  = current_user.user_id,
            db          = db,
        )
    except HallTicketServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Student self-view (Student — own PUBLISHED eligibility only)
# ---------------------------------------------------------------------------

@hallticket_router.get("/my-eligibility", response_model=MyEligibilityOut)
async def my_eligibility(
    semester_id:  UUID         = Query(...),
    current_user: CurrentUser  = Depends(require_roles(*_STUDENT)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
) -> MyEligibilityOut:
    try:
        return await HallTicketService.my_eligibility(
            student_id  = current_user.user_id,
            semester_id = semester_id,
            db          = db,
        )
    except HallTicketServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Batch generation (Admin / Dean)
# ---------------------------------------------------------------------------

@hallticket_router.post("/batches", response_model=HallTicketBatchOut, status_code=201)
async def generate_batch(
    body:         HallTicketBatchCreateIn,
    current_user: CurrentUser  = Depends(require_roles(*_MANAGERS)),
    db:           AsyncSession = Depends(get_tenant_db_dep),
) -> HallTicketBatchOut:
    try:
        return await HallTicketService.generate_batch(
            body,
            actor_id    = current_user.user_id,
            actor_role  = current_user.role,
            tenant_id   = current_user.tenant_id,
            schema_name = current_user.schema_name,
            db          = db,
        )
    except HallTicketServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# List batches (Admin / Dean)
# ---------------------------------------------------------------------------

@hallticket_router.get("/batches", response_model=list[HallTicketBatchOut])
async def list_batches(
    semester_id:  Optional[UUID] = Query(None),
    current_user: CurrentUser    = Depends(require_roles(*_MANAGERS)),
    db:           AsyncSession   = Depends(get_tenant_db_dep),
) -> list[HallTicketBatchOut]:
    try:
        return await HallTicketService.list_batches(semester_id, db)
    except HallTicketServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Individual hall ticket (Student own / Admin / Dean)
# ---------------------------------------------------------------------------

@hallticket_router.get("/ticket/{eligibility_id}", response_model=HallTicketOut)
async def get_hall_ticket(
    eligibility_id: UUID,
    current_user:   CurrentUser  = Depends(require_roles(
        TenantRole.STUDENT, TenantRole.ADMIN, TenantRole.DEAN
    )),
    db:             AsyncSession = Depends(get_tenant_db_dep),
) -> HallTicketOut:
    try:
        return await HallTicketService.get_hall_ticket(
            eligibility_id,
            requesting_user_id = current_user.user_id,
            requesting_role    = current_user.role,
            db                 = db,
        )
    except HallTicketServiceError as e:
        raise _err(e)
