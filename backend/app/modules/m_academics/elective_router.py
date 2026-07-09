from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m_academics.dean_scope import assert_dean_owns_semester_program
from app.modules.m_academics.elective_schemas import (
    AssignFacultyBody,
    DeanElectiveStatsOut,
    EligibleElectiveBasketOut,
    ElectiveOfferingCreate,
    ElectiveOfferingOut,
    ElectiveOfferingUpdate,
    ElectiveRegisterBody,
    ElectiveRegistrationOut,
    FacultyElectiveRosterOut,
)
from app.modules.m_academics.elective_service import ElectiveService
from app.modules.m_academics.service import AcadServiceError

router = APIRouter(tags=["electives"])

# Ownership: Electives are a Dean academic-authority responsibility end-to-end
# (create/edit/assign-faculty/open-close registration). Faculty NEVER create,
# propose, or approve offerings — they only teach the electives the Dean assigns
# and view the students who registered for them.
_MANAGERS = (TenantRole.DEAN,)


def _err(e: AcadServiceError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"error": e.code, "message": e.message})


# ---------------------------------------------------------------------------
# Dean — offering lifecycle
# ---------------------------------------------------------------------------

@router.get("/eligible-baskets", response_model=list[EligibleElectiveBasketOut])
async def list_eligible_baskets(
    semester_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[EligibleElectiveBasketOut]:
    await assert_dean_owns_semester_program(
        current_user.user_id, semester_id, db, "Semester not found in your governed programs.",
    )
    try:
        return await ElectiveService.list_eligible_baskets(semester_id, db)
    except AcadServiceError as e:
        raise _err(e)


@router.post("/offerings", response_model=ElectiveOfferingOut, status_code=201)
async def create_offering(
    body: ElectiveOfferingCreate,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveOfferingOut:
    try:
        offering = await ElectiveService.create_offering(
            body, current_user.user_id, db,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
        )
    except AcadServiceError as e:
        raise _err(e)
    rows = await ElectiveService.list_offerings_admin(db, semester_id=offering.semester_id)
    return next(r for r in rows if r["id"] == offering.id)


@router.post("/offerings/{offering_id}/assign-faculty", response_model=ElectiveOfferingOut)
async def assign_faculty(
    offering_id: UUID,
    body: AssignFacultyBody,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveOfferingOut:
    try:
        offering = await ElectiveService.assign_faculty(
            offering_id, body.course_id, body.faculty_user_id, current_user.user_id, db,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
        )
    except AcadServiceError as e:
        raise _err(e)
    rows = await ElectiveService.list_offerings_admin(db, semester_id=offering.semester_id)
    return next(r for r in rows if r["id"] == offering.id)


@router.get("/dashboard", response_model=DeanElectiveStatsOut)
async def dean_dashboard(
    semester_id: UUID | None = Query(None),
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> DeanElectiveStatsOut:
    return await ElectiveService.get_dashboard_stats(
        db, semester_id=semester_id,
        dean_id=current_user.user_id, actor_role=current_user.role,
    )


@router.get("/offerings", response_model=list[ElectiveOfferingOut])
async def list_offerings(
    semester_id: UUID | None = Query(None),
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN, TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ElectiveOfferingOut]:
    if current_user.role == TenantRole.STUDENT.value:
        rows = await ElectiveService.list_available_for_student(current_user.user_id, db, semester_id=semester_id)
    else:
        rows = await ElectiveService.list_offerings_admin(
            db, semester_id=semester_id,
            dean_id=current_user.user_id, actor_role=current_user.role,
        )
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


# ---------------------------------------------------------------------------
# Faculty — read-only roster of students who chose their elective(s)
# ---------------------------------------------------------------------------

@router.get("/faculty/roster", response_model=list[FacultyElectiveRosterOut])
async def faculty_roster(
    current_user: CurrentUser = Depends(require_roles(TenantRole.FACULTY)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[FacultyElectiveRosterOut]:
    return await ElectiveService.get_faculty_elective_roster(current_user.user_id, db)


# ---------------------------------------------------------------------------
# Student — register / drop / my electives
# ---------------------------------------------------------------------------

@router.post("/offerings/{offering_id}/register", response_model=ElectiveRegistrationOut, status_code=201)
async def register_elective(
    offering_id: UUID,
    body: ElectiveRegisterBody,
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ElectiveRegistrationOut:
    try:
        await ElectiveService.register(offering_id, body.course_id, current_user.user_id, db)
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
