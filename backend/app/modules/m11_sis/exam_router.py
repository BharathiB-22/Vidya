"""
SIS Examination Management — H59 FastAPI router.

Prefix: /exam   (mounted under /api/sis/ by m11_sis/router.py)

Routes (24 total):
  Centers      : POST /centers, GET /centers, GET /centers/{id}, PUT /centers/{id}
  Sessions     : POST /sessions, GET /sessions, GET /sessions/{id},
                 PUT /sessions/{id}, DELETE /sessions/{id},
                 POST /sessions/{id}/publish, /lock, /complete
  Schedules    : POST /sessions/{id}/schedules, GET /sessions/{id}/schedules,
                 PUT /schedules/{id}, DELETE /schedules/{id}
  Invigilation : POST /sessions/{id}/invigilation, GET /sessions/{id}/invigilation,
                 DELETE /invigilation/{id}, GET /my-invigilation
  Seating      : POST /sessions/{id}/allocate-seats, GET /sessions/{id}/seating
  Student      : GET /my-timetable, GET /my-hall-ticket

RBAC:
  _MANAGERS = ADMIN, DEAN   (all write operations + seating)
  _FACULTY  = FACULTY       (read own invigilation)
  _STUDENT  = STUDENT       (read own timetable + hall ticket)
  _ALL      = all 4 roles   (read sessions + schedules when PUBLISHED+)
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.exam_schemas import (
    ExamCenterCreateIn, ExamCenterOut, ExamCenterUpdateIn,
    ExamScheduleCreateIn, ExamScheduleOut, ExamScheduleUpdateIn,
    ExamSessionCreateIn, ExamSessionOut, ExamSessionUpdateIn,
    InvigilationCreateIn, InvigilationOut,
    MyHallTicketExamOut,
    SeatAllocationIn, SeatingAllocationResult,
    StudentSeatOut, StudentTimetableOut,
)
from app.modules.m11_sis.exam_service import (
    ExamCenterService,
    ExamInvigilationService,
    ExamScheduleService,
    ExamSeatingService,
    ExamServiceError,
    ExamSessionService,
    ExamStudentService,
)

exam_router = APIRouter(prefix="/exam", tags=["M11 SIS - Exam Management"])

_MANAGERS = (TenantRole.ADMIN, TenantRole.DEAN)
_FACULTY  = (TenantRole.FACULTY,)
_STUDENT  = (TenantRole.STUDENT,)
_ALL      = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY, TenantRole.STUDENT)


def _err(e: ExamServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Exam Centers
# ─────────────────────────────────────────────────────────────────────────────

@exam_router.post("/centers", response_model=ExamCenterOut, status_code=201)
async def create_center(
    body: ExamCenterCreateIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ExamCenterOut:
    try:
        return await ExamCenterService.create(
            body,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ExamServiceError as e:
        raise _err(e)


@exam_router.get("/centers", response_model=list[ExamCenterOut])
async def list_centers(
    include_inactive: bool = Query(False),
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS, *_FACULTY)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ExamCenterOut]:
    return await ExamCenterService.list_all(db, include_inactive)


@exam_router.get("/centers/{center_id}", response_model=ExamCenterOut)
async def get_center(
    center_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS, *_FACULTY)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ExamCenterOut:
    try:
        return await ExamCenterService.get(center_id, db)
    except ExamServiceError as e:
        raise _err(e)


@exam_router.put("/centers/{center_id}", response_model=ExamCenterOut)
async def update_center(
    center_id: UUID,
    body: ExamCenterUpdateIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ExamCenterOut:
    try:
        return await ExamCenterService.update(
            center_id, body,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ExamServiceError as e:
        raise _err(e)


# ─────────────────────────────────────────────────────────────────────────────
# Exam Sessions
# ─────────────────────────────────────────────────────────────────────────────

@exam_router.post("/sessions", response_model=ExamSessionOut, status_code=201)
async def create_session(
    body: ExamSessionCreateIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ExamSessionOut:
    try:
        return await ExamSessionService.create(
            body,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ExamServiceError as e:
        raise _err(e)


@exam_router.get("/sessions", response_model=list[ExamSessionOut])
async def list_sessions(
    semester_id:   Optional[UUID] = Query(None),
    status:        Optional[str]  = Query(None),
    session_type:  Optional[str]  = Query(None),
    current_user: CurrentUser = Depends(require_roles(*_ALL)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ExamSessionOut]:
    is_manager = current_user.role in _MANAGERS
    return await ExamSessionService.list_sessions(
        db,
        semester_id=semester_id,
        status_filter=status,
        session_type_filter=session_type,
        is_manager=is_manager,
    )


@exam_router.get("/sessions/{session_id}", response_model=ExamSessionOut)
async def get_session(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_ALL)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ExamSessionOut:
    is_manager = current_user.role in _MANAGERS
    try:
        return await ExamSessionService.get(session_id, db, is_manager=is_manager)
    except ExamServiceError as e:
        raise _err(e)


@exam_router.put("/sessions/{session_id}", response_model=ExamSessionOut)
async def update_session(
    session_id: UUID,
    body: ExamSessionUpdateIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ExamSessionOut:
    try:
        return await ExamSessionService.update(
            session_id, body,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ExamServiceError as e:
        raise _err(e)


@exam_router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> None:
    try:
        await ExamSessionService.delete(
            session_id,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ExamServiceError as e:
        raise _err(e)


@exam_router.post("/sessions/{session_id}/publish", response_model=ExamSessionOut)
async def publish_session(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ExamSessionOut:
    try:
        return await ExamSessionService.publish(
            session_id,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ExamServiceError as e:
        raise _err(e)


@exam_router.post("/sessions/{session_id}/lock", response_model=ExamSessionOut)
async def lock_session(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ExamSessionOut:
    try:
        return await ExamSessionService.lock(
            session_id,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ExamServiceError as e:
        raise _err(e)


@exam_router.post("/sessions/{session_id}/complete", response_model=ExamSessionOut)
async def complete_session(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ExamSessionOut:
    try:
        return await ExamSessionService.complete(
            session_id,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ExamServiceError as e:
        raise _err(e)


# ─────────────────────────────────────────────────────────────────────────────
# Exam Schedules
# ─────────────────────────────────────────────────────────────────────────────

@exam_router.post("/sessions/{session_id}/schedules",
                  response_model=ExamScheduleOut, status_code=201)
async def create_schedule(
    session_id: UUID,
    body: ExamScheduleCreateIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ExamScheduleOut:
    try:
        return await ExamScheduleService.create(
            session_id, body,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ExamServiceError as e:
        raise _err(e)


@exam_router.get("/sessions/{session_id}/schedules", response_model=list[ExamScheduleOut])
async def list_schedules(
    session_id: UUID,
    section_id: Optional[UUID] = Query(None),
    current_user: CurrentUser = Depends(require_roles(*_ALL)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ExamScheduleOut]:
    is_manager = current_user.role in _MANAGERS
    try:
        return await ExamScheduleService.list_schedules(
            db, session_id, section_id, is_manager=is_manager
        )
    except ExamServiceError as e:
        raise _err(e)


@exam_router.put("/schedules/{schedule_id}", response_model=ExamScheduleOut)
async def update_schedule(
    schedule_id: UUID,
    body: ExamScheduleUpdateIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ExamScheduleOut:
    try:
        return await ExamScheduleService.update(
            schedule_id, body,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ExamServiceError as e:
        raise _err(e)


@exam_router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> None:
    try:
        await ExamScheduleService.delete(
            schedule_id,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ExamServiceError as e:
        raise _err(e)


# ─────────────────────────────────────────────────────────────────────────────
# Invigilation
# ─────────────────────────────────────────────────────────────────────────────

@exam_router.post("/sessions/{session_id}/invigilation",
                  response_model=InvigilationOut, status_code=201)
async def assign_invigilation(
    session_id: UUID,
    body: InvigilationCreateIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> InvigilationOut:
    try:
        return await ExamInvigilationService.assign(
            session_id, body,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ExamServiceError as e:
        raise _err(e)


@exam_router.get("/sessions/{session_id}/invigilation", response_model=list[InvigilationOut])
async def list_invigilation(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[InvigilationOut]:
    try:
        return await ExamInvigilationService.list_for_session(db, session_id)
    except ExamServiceError as e:
        raise _err(e)


@exam_router.delete("/invigilation/{invigilation_id}", status_code=204)
async def delete_invigilation(
    invigilation_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> None:
    try:
        await ExamInvigilationService.delete(
            invigilation_id,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ExamServiceError as e:
        raise _err(e)


@exam_router.get("/my-invigilation", response_model=list[InvigilationOut])
async def my_invigilation(
    session_id: Optional[UUID] = Query(None),
    current_user: CurrentUser = Depends(require_roles(*_FACULTY)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[InvigilationOut]:
    return await ExamInvigilationService.my_invigilation(
        db, current_user.user_id, session_id
    )


# ─────────────────────────────────────────────────────────────────────────────
# Seat Allocation
# ─────────────────────────────────────────────────────────────────────────────

@exam_router.post("/sessions/{session_id}/allocate-seats",
                  response_model=SeatingAllocationResult)
async def allocate_seats(
    session_id: UUID,
    body: SeatAllocationIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SeatingAllocationResult:
    try:
        return await ExamSeatingService.allocate_seats(
            session_id, body,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except ExamServiceError as e:
        raise _err(e)


@exam_router.get("/sessions/{session_id}/seating", response_model=list[StudentSeatOut])
async def list_seating(
    session_id: UUID,
    section_id: Optional[UUID] = Query(None),
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[StudentSeatOut]:
    try:
        return await ExamSeatingService.list_seating(db, session_id, section_id)
    except ExamServiceError as e:
        raise _err(e)


# ─────────────────────────────────────────────────────────────────────────────
# Student views
# ─────────────────────────────────────────────────────────────────────────────

@exam_router.get("/my-timetable", response_model=StudentTimetableOut)
async def my_timetable(
    session_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_roles(*_STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> StudentTimetableOut:
    try:
        return await ExamStudentService.my_timetable(db, current_user.user_id, session_id)
    except ExamServiceError as e:
        raise _err(e)


@exam_router.get("/my-hall-ticket", response_model=MyHallTicketExamOut)
async def my_hall_ticket(
    session_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_roles(*_STUDENT)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> MyHallTicketExamOut:
    try:
        return await ExamStudentService.my_hall_ticket(db, current_user.user_id, session_id)
    except ExamServiceError as e:
        raise _err(e)
