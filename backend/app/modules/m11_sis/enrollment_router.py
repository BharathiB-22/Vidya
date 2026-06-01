"""
SIS Enrollment — M11-002 Router.

All routes are included into the main sis router (prefix /sis).

RBAC:
  _WRITE  = ADMIN only   (enroll, unenroll, move)
  _READ   = ADMIN, DEAN  (roster, student list, profile, dashboard)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.enrollment_schemas import (
    DashboardCountsOut,
    EnrollStudentIn,
    EnrollmentOut,
    MoveStudentIn,
    RosterStudentOut,
    StudentProfileOut,
    StudentSummaryOut,
)
from app.modules.m11_sis.enrollment_service import EnrollmentService, EnrollmentServiceError

enrollment_router = APIRouter(tags=["M11 SIS Enrollment"])

_WRITE = (TenantRole.ADMIN,)
_READ  = (TenantRole.ADMIN, TenantRole.DEAN)


def _err(e: EnrollmentServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@enrollment_router.get("/dashboard/counts", response_model=DashboardCountsOut)
async def get_dashboard_counts(
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> DashboardCountsOut:
    return await EnrollmentService.get_dashboard_counts(db)


# ---------------------------------------------------------------------------
# Section roster
# ---------------------------------------------------------------------------

@enrollment_router.get("/sections/{section_id}/roster", response_model=list[RosterStudentOut])
async def get_section_roster(
    section_id: UUID,
    include_inactive: bool = Query(False),
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[RosterStudentOut]:
    try:
        return await EnrollmentService.get_roster(section_id, db, include_inactive)
    except EnrollmentServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Student list (enroll-picker search)
# ---------------------------------------------------------------------------

@enrollment_router.get("/students", response_model=list[StudentSummaryOut])
async def list_students(
    search: str | None = Query(None, description="Filter by name or email"),
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[StudentSummaryOut]:
    return await EnrollmentService.list_students(db, search)


# ---------------------------------------------------------------------------
# Student academic profile
# ---------------------------------------------------------------------------

@enrollment_router.get("/students/{student_id}/profile", response_model=StudentProfileOut)
async def get_student_profile(
    student_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> StudentProfileOut:
    try:
        return await EnrollmentService.get_student_profile(student_id, db)
    except EnrollmentServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Enrollment mutations
# ---------------------------------------------------------------------------

@enrollment_router.post("/enrollments", response_model=EnrollmentOut, status_code=201)
async def enroll_student(
    body: EnrollStudentIn,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> EnrollmentOut:
    try:
        return await EnrollmentService.enroll_student(
            body, db,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
        )
    except EnrollmentServiceError as e:
        raise _err(e)


@enrollment_router.delete("/enrollments/{enrollment_id}", status_code=204)
async def unenroll_student(
    enrollment_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> None:
    try:
        await EnrollmentService.unenroll(
            enrollment_id, db,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
        )
    except EnrollmentServiceError as e:
        raise _err(e)


@enrollment_router.post("/enrollments/{enrollment_id}/move", response_model=EnrollmentOut)
async def move_student(
    enrollment_id: UUID,
    body: MoveStudentIn,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> EnrollmentOut:
    try:
        return await EnrollmentService.move_student(
            enrollment_id, body, db,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
        )
    except EnrollmentServiceError as e:
        raise _err(e)
