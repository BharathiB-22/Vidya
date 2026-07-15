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
    CourseWithAssignmentsOut,
    ValidSemestersOut,
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


@router.get("/valid-semesters", response_model=ValidSemestersOut)
async def get_valid_semesters(
    course_id: UUID = Query(..., description="Course to scope the semester picker to"),
    current_user: CurrentUser = Depends(require_roles(*_MANAGE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ValidSemestersOut:
    """Semesters valid for assigning faculty to this course — scoped to the
    course's own program so the Assign dialog can never offer an unrelated
    program's semester. DEAN/ADMIN only."""
    try:
        return await AssignmentService.list_valid_semesters(course_id, db)
    except AssignmentServiceError as e:
        raise _err(e)


@router.get("/faculty-list")
async def list_faculty_users(
    current_user: CurrentUser = Depends(require_roles(*_MANAGE)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    """Return all active FACULTY users — used by the assignment dialog. DEAN only."""
    from app.modules.m_academics.assignment_service import AssignmentService
    return await AssignmentService.list_faculty_users(
        caller_role=current_user.viewing_role, caller_user_id=current_user.user_id, db=db
    )


@router.get("", response_model=AssignmentListResponse)
async def list_assignments(
    course_id:        UUID | None         = Query(None, description="Filter by course (omit for all)"),
    semester_id:      UUID | None         = Query(None, description="Optionally filter by semester"),
    section_id:       UUID | None         = Query(None, description="Optionally filter by section"),
    include_inactive: bool                = Query(False, description="Include revoked assignments"),
    current_user: CurrentUser             = Depends(require_roles(*_READ)),
    db: AsyncSession                      = Depends(get_tenant_db_dep),
) -> AssignmentListResponse:
    """List assignments for a course or all courses. DEAN/ADMIN only."""
    try:
        if course_id is not None:
            return await AssignmentService.list_by_course(
                course_id,
                semester_id=semester_id,
                section_id=section_id,
                include_inactive=include_inactive,
                caller_role=current_user.viewing_role,
                caller_user_id=current_user.user_id,
                db=db,
            )
        return await AssignmentService.list_all(
            semester_id=semester_id,
            section_id=section_id,
            include_inactive=include_inactive,
            caller_role=current_user.viewing_role,
            caller_user_id=current_user.user_id,
            db=db,
        )
    except AssignmentServiceError as e:
        raise _err(e)


@router.get("/courses-for-slot", response_model=list[CourseWithAssignmentsOut])
async def list_courses_for_slot(
    semester_id: UUID = Query(..., description="Operational semester to scope courses to"),
    section_id:  UUID | None = Query(None),
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[CourseWithAssignmentsOut]:
    """Every course in this semester's program, each with its (possibly
    empty) assignments — powers the Timetable slot picker so a course with
    no faculty assigned yet is still selectable. DEAN/ADMIN only."""
    return await AssignmentService.list_courses_with_assignments(
        semester_id, section_id=section_id, db=db,
    )


@router.get("/mine", response_model=AssignmentListResponse)
async def list_my_assignments(
    include_inactive: bool       = Query(False),
    current_user: CurrentUser    = Depends(require_roles(TenantRole.FACULTY, TenantRole.DEAN)),
    db: AsyncSession             = Depends(get_tenant_db_dep),
) -> AssignmentListResponse:
    """Return course assignments for the calling FACULTY or DEAN-with-FACULTY user."""
    try:
        return await AssignmentService.list_my_courses(
            current_user.user_id,
            include_inactive=include_inactive,
            db=db,
        )
    except AssignmentServiceError as e:
        raise _err(e)
