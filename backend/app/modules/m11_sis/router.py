from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.attendance_router import attendance_router
from app.modules.m11_sis.directory_router import directory_router
from app.modules.m11_sis.enrollment_router import enrollment_router
from app.modules.m11_sis.exam_router import exam_router
from app.modules.m11_sis.hallticket_router import hallticket_router
from app.modules.m11_sis.marks_router import marks_router
from app.modules.m11_sis.me_router import me_router
from app.modules.m11_sis.results_router import results_router
from app.modules.m11_sis.rollover_router import rollover_router
from app.modules.m11_sis.schemas import SchoolCreate, SchoolOut, SchoolUpdate
from app.modules.m11_sis.service import SchoolService, SchoolServiceError

router = APIRouter(tags=["M11 SIS"])
router.include_router(enrollment_router)
router.include_router(directory_router)
router.include_router(me_router)
router.include_router(rollover_router)
router.include_router(attendance_router)
router.include_router(marks_router)
router.include_router(hallticket_router)
router.include_router(exam_router)
router.include_router(results_router)

_WRITE = (TenantRole.ADMIN, TenantRole.DEAN)
_READ  = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY, TenantRole.STUDENT)


def _err(e: SchoolServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


@router.get("/schools", response_model=list[SchoolOut])
async def list_schools(
    include_inactive: bool = Query(False),
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[SchoolOut]:
    rows = await SchoolService.list_schools(db, include_inactive=include_inactive)
    return [SchoolOut.model_validate(r) for r in rows]


@router.post("/schools", response_model=SchoolOut, status_code=201)
async def create_school(
    body: SchoolCreate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SchoolOut:
    try:
        school = await SchoolService.create_school(
            body,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except SchoolServiceError as e:
        raise _err(e)
    return SchoolOut.model_validate(school)


@router.get("/schools/{school_id}", response_model=SchoolOut)
async def get_school(
    school_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SchoolOut:
    try:
        school = await SchoolService.get_school(school_id, db)
    except SchoolServiceError as e:
        raise _err(e)
    return SchoolOut.model_validate(school)


@router.put("/schools/{school_id}", response_model=SchoolOut)
async def update_school(
    school_id: UUID,
    body: SchoolUpdate,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SchoolOut:
    try:
        school = await SchoolService.update_school(
            school_id,
            body,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except SchoolServiceError as e:
        raise _err(e)
    return SchoolOut.model_validate(school)


@router.delete("/schools/{school_id}", status_code=204)
async def delete_school(
    school_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> None:
    try:
        await SchoolService.delete_school(
            school_id,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except SchoolServiceError as e:
        raise _err(e)
