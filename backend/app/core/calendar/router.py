from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.calendar.schemas import (
    AcademicEventCreate,
    AcademicEventOut,
    AcademicEventUpdate,
    CalendarItem,
    TeachingDays,
)
from app.core.calendar.service import CalendarService, CalendarServiceError

router = APIRouter(tags=["calendar"])

_MANAGERS = (TenantRole.ADMIN, TenantRole.DEAN)


def _err(e: CalendarServiceError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"error": e.code, "message": e.message})


@router.get("/me", response_model=list[CalendarItem])
async def get_my_calendar(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[CalendarItem]:
    today = date.today()
    date_from = date_from or today
    date_to = date_to or (today + timedelta(days=60))
    return await CalendarService.get_student_calendar(current_user.user_id, date_from, date_to, db)


@router.get("/me/teaching-days", response_model=TeachingDays)
async def get_my_teaching_days(
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TeachingDays:
    """Which weekdays this student has class on, so the calendar can grey out the
    ones they do not — without assuming Saturday is a holiday for everybody."""
    days = await CalendarService.get_teaching_days(current_user.user_id, db)
    return TeachingDays(teaching_days=days)


@router.post("/me/events", response_model=AcademicEventOut, status_code=201)
async def create_my_personal_event(
    body: AcademicEventCreate,
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> AcademicEventOut:
    """A student adds their own academic event to their own calendar.

    Deliberately separate from the managers' /events: the service forces this to
    PERSONAL visibility, so nothing a student writes can land on anyone else's
    calendar regardless of what the request body says.
    """
    ev = await CalendarService.create_personal_event(body, current_user.user_id, db)
    return AcademicEventOut.model_validate(ev)


@router.delete("/me/events/{event_id}", status_code=204)
async def delete_my_personal_event(
    event_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> None:
    try:
        await CalendarService.delete_personal_event(event_id, current_user.user_id, db)
    except CalendarServiceError as e:
        raise _err(e)


@router.post("/events", response_model=AcademicEventOut, status_code=201)
async def create_event(
    body: AcademicEventCreate,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> AcademicEventOut:
    ev = await CalendarService.create_event(body, current_user.user_id, db)
    return AcademicEventOut.model_validate(ev)


@router.get("/events", response_model=list[AcademicEventOut])
async def list_events(
    _: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[AcademicEventOut]:
    rows = await CalendarService.list_events(db)
    return [AcademicEventOut.model_validate(r) for r in rows]


@router.patch("/events/{event_id}", response_model=AcademicEventOut)
async def update_event(
    event_id: UUID,
    body: AcademicEventUpdate,
    _: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> AcademicEventOut:
    try:
        ev = await CalendarService.update_event(event_id, body, db)
        return AcademicEventOut.model_validate(ev)
    except CalendarServiceError as e:
        raise _err(e)


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(
    event_id: UUID,
    _: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> None:
    try:
        await CalendarService.delete_event(event_id, db)
    except CalendarServiceError as e:
        raise _err(e)
