"""
SIS Self-Service Router — H51.

Routes mounted at /sis/me/* by the main SIS router.
Each user can read and edit only their own profile.

RBAC:
  /me/student-profile  — TenantRole.STUDENT only
  /me/faculty-profile  — TenantRole.FACULTY only

Admin/Dean profile management remains on /sis/directory/* endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.directory_schemas import (
    FacultyDetailOut,
    FacultySelfServiceUpdate,
    StudentDetailOut,
    StudentSelfServiceUpdate,
)
from app.modules.m11_sis.directory_service import (
    DirectoryServiceError,
    FacultyDirectoryService,
    StudentDirectoryService,
)

me_router = APIRouter(tags=["M11 SIS Self-Service"])


def _err(e: DirectoryServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


# ---------------------------------------------------------------------------
# Student self-service
# ---------------------------------------------------------------------------

@me_router.get("/me/student-profile", response_model=StudentDetailOut)
async def get_my_student_profile(
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        return await StudentDirectoryService.get_detail(current_user.user_id, db)
    except DirectoryServiceError as e:
        raise _err(e)


@me_router.put("/me/student-profile", response_model=StudentDetailOut)
async def update_my_student_profile(
    body: StudentSelfServiceUpdate,
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        return await StudentDirectoryService.upsert_own_profile(
            current_user_id=current_user.user_id,
            body=body,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except DirectoryServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Faculty self-service
# ---------------------------------------------------------------------------

@me_router.get("/me/faculty-profile", response_model=FacultyDetailOut)
async def get_my_faculty_profile(
    current_user: CurrentUser = Depends(require_roles(TenantRole.FACULTY)),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        return await FacultyDirectoryService.get_detail(current_user.user_id, db)
    except DirectoryServiceError as e:
        raise _err(e)


@me_router.put("/me/faculty-profile", response_model=FacultyDetailOut)
async def update_my_faculty_profile(
    body: FacultySelfServiceUpdate,
    current_user: CurrentUser = Depends(require_roles(TenantRole.FACULTY)),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        return await FacultyDirectoryService.upsert_own_profile(
            current_user_id=current_user.user_id,
            body=body,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except DirectoryServiceError as e:
        raise _err(e)
