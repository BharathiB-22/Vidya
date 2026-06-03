"""
SIS Directory Router — H50.

Routes mounted at /sis/directory/* by the main SIS router.

RBAC:
  _WRITE  = ADMIN, DEAN          (profile upserts)
  _READ   = ADMIN, DEAN, FACULTY (all list and detail endpoints)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.directory_schemas import (
    DirectoryPage,
    FacultyDetailOut,
    FacultyDirectoryItem,
    FacultyProfileUpsert,
    StudentDetailOut,
    StudentDirectoryItem,
    StudentProfileUpsert,
)
from app.modules.m11_sis.directory_service import (
    DirectoryServiceError,
    FacultyDirectoryService,
    StudentDirectoryService,
)

directory_router = APIRouter(tags=["M11 SIS Directory"])

_WRITE = (TenantRole.ADMIN, TenantRole.DEAN)
_READ  = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)


def _err(e: DirectoryServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


# ---------------------------------------------------------------------------
# Student directory
# ---------------------------------------------------------------------------

@directory_router.get("/directory/students", response_model=DirectoryPage[StudentDirectoryItem])
async def list_student_directory(
    page:       int            = Query(1,    ge=1),
    page_size:  int            = Query(20,   ge=1, le=100),
    search:     str | None     = Query(None, description="Filter by name, email, or USN"),
    program_id: UUID | None    = Query(None),
    batch_id:   UUID | None    = Query(None),
    section_id: UUID | None    = Query(None),
    is_active:  bool | None    = Query(None),
    current_user: CurrentUser  = Depends(require_roles(*_READ)),
    db: AsyncSession           = Depends(get_tenant_db_dep),
):
    return await StudentDirectoryService.list_directory(
        db,
        page=page,
        page_size=page_size,
        search=search,
        program_id=program_id,
        batch_id=batch_id,
        section_id=section_id,
        is_active=is_active,
    )


@directory_router.get("/directory/students/{user_id}", response_model=StudentDetailOut)
async def get_student_detail(
    user_id:      UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    try:
        return await StudentDirectoryService.get_detail(user_id, db)
    except DirectoryServiceError as e:
        raise _err(e)


@directory_router.put("/directory/students/{user_id}/profile", response_model=StudentDetailOut)
async def upsert_student_profile(
    user_id:      UUID,
    body:         StudentProfileUpsert,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    try:
        return await StudentDirectoryService.upsert_profile(
            user_id,
            body,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except DirectoryServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Faculty directory
# ---------------------------------------------------------------------------

@directory_router.get("/directory/faculty", response_model=DirectoryPage[FacultyDirectoryItem])
async def list_faculty_directory(
    page:          int            = Query(1,    ge=1),
    page_size:     int            = Query(20,   ge=1, le=100),
    search:        str | None     = Query(None, description="Filter by name, email, or employee ID"),
    department_id: UUID | None    = Query(None),
    is_active:     bool | None    = Query(None),
    current_user:  CurrentUser    = Depends(require_roles(*_READ)),
    db: AsyncSession              = Depends(get_tenant_db_dep),
):
    return await FacultyDirectoryService.list_directory(
        db,
        page=page,
        page_size=page_size,
        search=search,
        department_id=department_id,
        is_active=is_active,
    )


@directory_router.get("/directory/faculty/{user_id}", response_model=FacultyDetailOut)
async def get_faculty_detail(
    user_id:      UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    try:
        return await FacultyDirectoryService.get_detail(user_id, db)
    except DirectoryServiceError as e:
        raise _err(e)


@directory_router.put("/directory/faculty/{user_id}/profile", response_model=FacultyDetailOut)
async def upsert_faculty_profile(
    user_id:      UUID,
    body:         FacultyProfileUpsert,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    try:
        return await FacultyDirectoryService.upsert_profile(
            user_id,
            body,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except DirectoryServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Department faculty list
# ---------------------------------------------------------------------------

@directory_router.get("/departments/{dept_id}/faculty", response_model=DirectoryPage[FacultyDirectoryItem])
async def list_department_faculty(
    dept_id:      UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
):
    return await FacultyDirectoryService.list_by_department(dept_id, db)
