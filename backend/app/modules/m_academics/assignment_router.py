"""Subject Assignment — router (H-31).

RBAC
----
  _MANAGE = DEAN, ADMIN  (create, revoke — academic governance)
  _READ   = DEAN, ADMIN  (list by course/semester — management view)
  _MINE   = FACULTY only  (GET /mine — returns caller's own assignments)

Dean and Admin may assign or revoke faculty from courses.
Faculty cannot self-assign; they can only read their own assignments.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m_academics.assignment_schemas import (
    AssignmentCreate,
    AssignmentListResponse,
    AssignmentOut,
    AssignmentRevokeRequest,
)
from app.modules.m_academics.assignment_service import AssignmentService, AssignmentServiceError

router = APIRouter(tags=["course-assignments"])

_MANAGE = (TenantRole.DEAN, TenantRole.ADMIN)
_READ   = (TenantRole.DEAN, TenantRole.ADMIN)


def _err(e: AssignmentServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


@router.post("", response_model=AssignmentOut, status_code=201)
async def create_assignment(
    body: AssignmentCreate,
    current_user: CurrentUser = Depends(require_roles(*_MANAGE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> AssignmentOut:
    """Assign a FACULTY user to a course for a semester. DEAN/ADMIN only."""
    try:
        return await AssignmentService.create(
            body,
            assigned_by=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except AssignmentServiceError as e:
        raise _err(e)


@router.post("/{assignment_id}/revoke", response_model=AssignmentOut)
async def revoke_assignment(
    assignment_id: UUID,
    body: AssignmentRevokeRequest = AssignmentRevokeRequest(),
    current_user: CurrentUser = Depends(require_roles(*_MANAGE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> AssignmentOut:
    """Soft-revoke a faculty assignment. DEAN/ADMIN only."""
    try:
        return await AssignmentService.revoke(
            assignment_id,
            revoked_by=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except AssignmentServiceError as e:
        raise _err(e)


@router.get("/faculty-list")
async def list_faculty_users(
    current_user: CurrentUser = Depends(require_roles(*_MANAGE)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    """Return all active FACULTY users — used by the assignment dialog. DEAN only."""
    from app.modules.m_academics.assignment_service import AssignmentService
    return await AssignmentService.list_faculty_users(db=db)


@router.get("", response_model=AssignmentListResponse)
async def list_assignments(
    course_id:        UUID                = Query(..., description="Filter by course"),
    semester_id:      UUID | None         = Query(None, description="Optionally filter by semester"),
    include_inactive: bool                = Query(False, description="Include revoked assignments"),
    current_user: CurrentUser             = Depends(require_roles(*_READ)),
    db: AsyncSession                      = Depends(get_tenant_db_dep),
) -> AssignmentListResponse:
    """List all assignments for a course. DEAN/ADMIN only."""
    try:
        return await AssignmentService.list_by_course(
            course_id,
            semester_id=semester_id,
            include_inactive=include_inactive,
            db=db,
        )
    except AssignmentServiceError as e:
        raise _err(e)


@router.get("/mine", response_model=AssignmentListResponse)
async def list_my_assignments(
    include_inactive: bool       = Query(False),
    current_user: CurrentUser    = Depends(require_roles(TenantRole.FACULTY)),
    db: AsyncSession             = Depends(get_tenant_db_dep),
) -> AssignmentListResponse:
    """Return all course assignments for the calling FACULTY user."""
    try:
        return await AssignmentService.list_my_courses(
            current_user.user_id,
            include_inactive=include_inactive,
            db=db,
        )
    except AssignmentServiceError as e:
        raise _err(e)
