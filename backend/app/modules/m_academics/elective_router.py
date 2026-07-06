from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m_academics.elective_schemas import (
    ElectiveOfferingCreate,
    ElectiveOfferingOut,
    ElectiveOfferingPropose,
    ElectiveOfferingUpdate,
    ElectiveRegistrationOut,
    ElectiveRejectBody,
)
from app.modules.m_academics.elective_service import ElectiveService
from app.modules.m_academics.service import AcadServiceError

router = APIRouter(tags=["electives"])

# Ownership correction: Electives are a Dean academic-authority responsibility
# end-to-end (create/edit/open-close registration/approve final list/publish).
# Admin no longer creates, edits, approves, or publishes electives.
_MANAGERS = (TenantRole.DEAN,)


def _err(e: AcadServiceError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"error": e.code, "message": e.message})


@router.post("/offerings", response_model=ElectiveOfferingOut, status_code=201)
async def create_offering(
    body: ElectiveOfferingCreate,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveOfferingOut:
    try:
        offering = await ElectiveService.create_offering(body, current_user.user_id, db)
    except AcadServiceError as e:
        raise _err(e)
    rows = await ElectiveService.list_offerings_admin(db, semester_id=offering.semester_id)
    return next(r for r in rows if r["id"] == offering.id)


@router.post("/offerings/propose", response_model=ElectiveOfferingOut, status_code=201)
async def propose_offering(
    body: ElectiveOfferingPropose,
    current_user: CurrentUser = Depends(require_roles(TenantRole.FACULTY)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveOfferingOut:
    try:
        offering = await ElectiveService.propose_offering(body, current_user.user_id, db)
    except AcadServiceError as e:
        raise _err(e)
    rows = await ElectiveService.list_mine_for_faculty(current_user.user_id, db)
    return next(r for r in rows if r["id"] == offering.id)


@router.get("/offerings/mine", response_model=list[ElectiveOfferingOut])
async def list_my_proposed_offerings(
    current_user: CurrentUser = Depends(require_roles(TenantRole.FACULTY)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ElectiveOfferingOut]:
    return await ElectiveService.list_mine_for_faculty(current_user.user_id, db)


@router.get("/offerings/pending", response_model=list[ElectiveOfferingOut])
async def list_pending_offerings(
    _: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ElectiveOfferingOut]:
    return await ElectiveService.list_pending_for_dean(db)


@router.get("/offerings/approved", response_model=list[ElectiveOfferingOut])
async def list_approved_offerings(
    _: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ElectiveOfferingOut]:
    return await ElectiveService.list_approved_for_admin(db)


@router.post("/offerings/{offering_id}/approve", response_model=ElectiveOfferingOut)
async def approve_offering(
    offering_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveOfferingOut:
    try:
        offering = await ElectiveService.approve_offering(offering_id, current_user.user_id, db)
    except AcadServiceError as e:
        raise _err(e)
    rows = await ElectiveService.list_approved_for_admin(db)
    return next(r for r in rows if r["id"] == offering.id)


@router.post("/offerings/{offering_id}/reject", response_model=ElectiveOfferingOut)
async def reject_offering(
    offering_id: UUID,
    body: ElectiveRejectBody,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveOfferingOut:
    try:
        offering = await ElectiveService.reject_offering(offering_id, current_user.user_id, body.reason, db)
    except AcadServiceError as e:
        raise _err(e)
    rows = await ElectiveService.list_offerings_admin(db, semester_id=offering.semester_id)
    return next(r for r in rows if r["id"] == offering.id)


@router.post("/offerings/{offering_id}/publish", response_model=ElectiveOfferingOut)
async def publish_offering(
    offering_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveOfferingOut:
    try:
        offering = await ElectiveService.publish_offering(offering_id, current_user.user_id, db)
    except AcadServiceError as e:
        raise _err(e)
    rows = await ElectiveService.list_offerings_admin(db, semester_id=offering.semester_id)
    return next(r for r in rows if r["id"] == offering.id)


@router.get("/offerings", response_model=list[ElectiveOfferingOut])
async def list_offerings(
    semester_id: UUID | None = Query(None),
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN, TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ElectiveOfferingOut]:
    if current_user.role == TenantRole.STUDENT.value:
        rows = await ElectiveService.list_available_for_student(current_user.user_id, db, semester_id=semester_id)
    else:
        rows = await ElectiveService.list_offerings_admin(db, semester_id=semester_id)
    return rows


@router.patch("/offerings/{offering_id}", response_model=ElectiveOfferingOut)
async def update_offering(
    offering_id: UUID,
    body: ElectiveOfferingUpdate,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveOfferingOut:
    try:
        offering = await ElectiveService.update_offering(offering_id, current_user.user_id, body, db)
    except AcadServiceError as e:
        raise _err(e)
    rows = await ElectiveService.list_offerings_admin(db, semester_id=offering.semester_id)
    return next(r for r in rows if r["id"] == offering.id)


@router.post("/offerings/{offering_id}/register", response_model=ElectiveRegistrationOut, status_code=201)
async def register_elective(
    offering_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveRegistrationOut:
    try:
        await ElectiveService.register(offering_id, current_user.user_id, db)
    except AcadServiceError as e:
        raise _err(e)
    rows = await ElectiveService.get_my_registrations(current_user.user_id, db)
    return next(r for r in rows if r["offering_id"] == offering_id)


@router.post("/offerings/{offering_id}/drop", response_model=ElectiveRegistrationOut)
async def drop_elective(
    offering_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveRegistrationOut:
    try:
        await ElectiveService.drop(offering_id, current_user.user_id, db)
    except AcadServiceError as e:
        raise _err(e)
    rows = await ElectiveService.get_my_registrations(current_user.user_id, db)
    return next(r for r in rows if r["offering_id"] == offering_id)


@router.get("/me", response_model=list[ElectiveRegistrationOut])
async def my_electives(
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ElectiveRegistrationOut]:
    return await ElectiveService.get_my_registrations(current_user.user_id, db)
