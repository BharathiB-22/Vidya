"""Elective endpoints.

The slot and its choices are curriculum, created and published under
Program -> Elective Basket (m01_program_advisor). What lives here is everything
that is *per running term* rather than per curriculum: which faculty teaches
each choice this year, which option each student picked, and the combined class
that results.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m_academics.elective_schemas import (
    AssignChoiceFacultyBody,
    DeanElectiveSlotOut,
    ElectiveRegisterBody,
    ElectiveRegistrationOut,
    ElectiveSlotOut,
    FacultyElectiveRosterOut,
)
from app.modules.m_academics.elective_service import ElectiveService
from app.modules.m_academics.service import AcadServiceError

router = APIRouter(tags=["electives"])


def _err(e: AcadServiceError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"error": e.code, "message": e.message})


# ---------------------------------------------------------------------------
# Dean — faculty per choice, per term. The curriculum is untouched: Odd-2026 and
# Odd-2027 may put different faculty on the same elective.
# ---------------------------------------------------------------------------

@router.get("/slots/by-term", response_model=list[DeanElectiveSlotOut])
async def list_slots_for_term(
    semester_id: UUID = Query(..., description="The running term to assign faculty for"),
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[DeanElectiveSlotOut]:
    try:
        return await ElectiveService.list_slots_for_term(semester_id, current_user.user_id, db)
    except AcadServiceError as e:
        raise _err(e)


@router.post("/slots/by-term/{semester_id}/assign-faculty", status_code=200)
async def assign_choice_faculty(
    semester_id: UUID,
    body: AssignChoiceFacultyBody,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    try:
        await ElectiveService.assign_choice_faculty(
            body.course_id, semester_id, body.faculty_user_id, current_user.user_id, db,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
        )
    except AcadServiceError as e:
        raise _err(e)
    return {"status": "assigned"}


# ---------------------------------------------------------------------------
# Faculty — read-only roster of the students who chose their elective.
# ---------------------------------------------------------------------------

@router.get("/faculty/roster", response_model=list[FacultyElectiveRosterOut])
async def faculty_roster(
    current_user: CurrentUser = Depends(require_roles(TenantRole.FACULTY)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[FacultyElectiveRosterOut]:
    return await ElectiveService.get_faculty_elective_roster(current_user.user_id, db)


# ---------------------------------------------------------------------------
# Student — see this semester's slots, choose one option per slot, drop.
# ---------------------------------------------------------------------------

@router.get("/slots", response_model=list[ElectiveSlotOut])
async def my_elective_slots(
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ElectiveSlotOut]:
    return await ElectiveService.list_slots_for_student(current_user.user_id, db)


@router.post("/slots/{basket_id}/register", response_model=ElectiveRegistrationOut, status_code=201)
async def register_elective(
    basket_id: UUID,
    body: ElectiveRegisterBody,
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveRegistrationOut:
    try:
        await ElectiveService.register(basket_id, body.course_id, current_user.user_id, db)
    except AcadServiceError as e:
        raise _err(e)
    rows = await ElectiveService.get_my_registrations(current_user.user_id, db)
    return next(r for r in rows if r["basket_id"] == basket_id)


@router.post("/slots/{basket_id}/drop", response_model=ElectiveRegistrationOut)
async def drop_elective(
    basket_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveRegistrationOut:
    try:
        await ElectiveService.drop(basket_id, current_user.user_id, db)
    except AcadServiceError as e:
        raise _err(e)
    rows = await ElectiveService.get_my_registrations(current_user.user_id, db)
    return next(r for r in rows if r["basket_id"] == basket_id)


@router.get("/me", response_model=list[ElectiveRegistrationOut])
async def my_electives(
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ElectiveRegistrationOut]:
    return await ElectiveService.get_my_registrations(current_user.user_id, db)
