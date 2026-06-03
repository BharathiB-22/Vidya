"""
SIS Attendance — H55 Router.

RBAC summary:
  _FACULTY_WRITE = FACULTY only      (create session, mark, edit record)
  _MANAGERS      = ADMIN, DEAN       (reopen, analytics, shortage report)
  _READERS       = FACULTY, ADMIN, DEAN (list sessions, view records, section analytics)
  _STUDENT       = STUDENT only      (self-view)

Service-level guards enforce that FACULTY can only operate on their own sessions.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.attendance_repository import DEFAULT_SHORTAGE_THRESHOLD
from app.modules.m11_sis.attendance_schemas import (
    AttendanceDashboardOut, AttendanceMarkIn, AttendanceMarkResult, AttendanceRecordOut,
    MyCourseAttendanceDetail, MyAttendanceSummary,
    RecordEditIn, ReopenSessionIn,
    SectionAttendanceOut, SessionCreateIn, SessionOut, SessionUpdateIn,
    ShortageReportOut,
)
from app.modules.m11_sis.attendance_service import AttendanceService, AttendanceServiceError

attendance_router = APIRouter(tags=["M11 SIS Attendance"])

_FACULTY_WRITE = (TenantRole.FACULTY,)
_MANAGERS      = (TenantRole.ADMIN, TenantRole.DEAN)
_READERS       = (TenantRole.FACULTY, TenantRole.ADMIN, TenantRole.DEAN)
_STUDENT       = (TenantRole.STUDENT,)


def _err(e: AttendanceServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


# ---------------------------------------------------------------------------
# Sessions — CRUD
# ---------------------------------------------------------------------------

@attendance_router.post("/attendance/sessions", response_model=SessionOut, status_code=201)
async def create_session(
    body: SessionCreateIn,
    current_user: CurrentUser = Depends(require_roles(*_FACULTY_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SessionOut:
    try:
        return await AttendanceService.create_session(
            body,
            actor_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except AttendanceServiceError as e:
        raise _err(e)


@attendance_router.get("/attendance/sessions", response_model=list[SessionOut])
async def list_sessions(
    course_id:  Optional[UUID] = Query(None),
    section_id: Optional[UUID] = Query(None),
    date_from:  Optional[str]  = Query(None, description="YYYY-MM-DD"),
    date_to:    Optional[str]  = Query(None, description="YYYY-MM-DD"),
    status:     Optional[str]  = Query(None, description="OPEN or LOCKED"),
    current_user: CurrentUser  = Depends(require_roles(*_READERS)),
    db: AsyncSession           = Depends(get_tenant_db_dep),
) -> list[SessionOut]:
    try:
        return await AttendanceService.list_sessions(
            actor_id=current_user.user_id,
            actor_role=current_user.role,
            course_id=course_id,
            section_id=section_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
            db=db,
        )
    except AttendanceServiceError as e:
        raise _err(e)


@attendance_router.get("/attendance/sessions/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SessionOut:
    try:
        return await AttendanceService.get_session(
            session_id,
            actor_id=current_user.user_id,
            actor_role=current_user.role,
            db=db,
        )
    except AttendanceServiceError as e:
        raise _err(e)


@attendance_router.put("/attendance/sessions/{session_id}", response_model=SessionOut)
async def update_session(
    session_id: UUID,
    body: SessionUpdateIn,
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SessionOut:
    try:
        return await AttendanceService.update_session(
            session_id, body,
            actor_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except AttendanceServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Records — view and mark
# ---------------------------------------------------------------------------

@attendance_router.get("/attendance/sessions/{session_id}/records", response_model=list[AttendanceRecordOut])
async def get_session_records(
    session_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[AttendanceRecordOut]:
    try:
        return await AttendanceService.get_session_records(
            session_id,
            actor_id=current_user.user_id,
            actor_role=current_user.role,
            db=db,
        )
    except AttendanceServiceError as e:
        raise _err(e)


@attendance_router.post("/attendance/sessions/{session_id}/mark", response_model=AttendanceMarkResult)
async def mark_attendance(
    session_id: UUID,
    body: AttendanceMarkIn,
    threshold:  float = Query(DEFAULT_SHORTAGE_THRESHOLD, description="Shortage warning threshold %"),
    current_user: CurrentUser = Depends(require_roles(*_FACULTY_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> AttendanceMarkResult:
    try:
        return await AttendanceService.mark_attendance(
            session_id, body,
            actor_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
            threshold=threshold,
        )
    except AttendanceServiceError as e:
        raise _err(e)


@attendance_router.patch(
    "/attendance/sessions/{session_id}/records/{record_id}",
    response_model=AttendanceRecordOut,
)
async def edit_record(
    session_id: UUID,
    record_id:  UUID,
    body: RecordEditIn,
    threshold:  float = Query(DEFAULT_SHORTAGE_THRESHOLD),
    current_user: CurrentUser = Depends(require_roles(*_FACULTY_WRITE)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> AttendanceRecordOut:
    try:
        return await AttendanceService.edit_record(
            session_id, record_id, body,
            actor_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
            threshold=threshold,
        )
    except AttendanceServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Reopen — ADMIN / DEAN only
# ---------------------------------------------------------------------------

@attendance_router.post("/attendance/sessions/{session_id}/reopen", response_model=SessionOut)
async def reopen_session(
    session_id: UUID,
    body: ReopenSessionIn,
    current_user: CurrentUser = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SessionOut:
    try:
        return await AttendanceService.reopen_session(
            session_id, body,
            actor_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except AttendanceServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Analytics — ADMIN / DEAN
# ---------------------------------------------------------------------------

@attendance_router.get("/attendance/analytics/dashboard", response_model=AttendanceDashboardOut)
async def get_dashboard(
    semester_id: Optional[UUID] = Query(None),
    threshold:   float          = Query(DEFAULT_SHORTAGE_THRESHOLD),
    current_user: CurrentUser   = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession            = Depends(get_tenant_db_dep),
) -> AttendanceDashboardOut:
    try:
        return await AttendanceService.get_dashboard(
            threshold=threshold, semester_id=semester_id, db=db
        )
    except AttendanceServiceError as e:
        raise _err(e)


@attendance_router.get("/attendance/analytics/shortage", response_model=ShortageReportOut)
async def get_shortage_report(
    threshold:   float          = Query(DEFAULT_SHORTAGE_THRESHOLD),
    semester_id: Optional[UUID] = Query(None),
    section_id:  Optional[UUID] = Query(None),
    course_id:   Optional[UUID] = Query(None),
    current_user: CurrentUser   = Depends(require_roles(*_MANAGERS)),
    db: AsyncSession            = Depends(get_tenant_db_dep),
) -> ShortageReportOut:
    try:
        return await AttendanceService.get_shortage_report(
            threshold=threshold,
            semester_id=semester_id,
            section_id=section_id,
            course_id=course_id,
            db=db,
        )
    except AttendanceServiceError as e:
        raise _err(e)


@attendance_router.get("/attendance/analytics/section/{section_id}", response_model=SectionAttendanceOut)
async def get_section_analytics(
    section_id: UUID,
    threshold:  float          = Query(DEFAULT_SHORTAGE_THRESHOLD),
    current_user: CurrentUser  = Depends(require_roles(*_READERS)),
    db: AsyncSession           = Depends(get_tenant_db_dep),
) -> SectionAttendanceOut:
    try:
        return await AttendanceService.get_section_analytics(section_id, threshold, db)
    except AttendanceServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Student self-view
# ---------------------------------------------------------------------------

@attendance_router.get("/attendance/me", response_model=MyAttendanceSummary)
async def get_my_attendance(
    threshold:    float         = Query(DEFAULT_SHORTAGE_THRESHOLD),
    current_user: CurrentUser   = Depends(require_roles(*_STUDENT)),
    db: AsyncSession            = Depends(get_tenant_db_dep),
) -> MyAttendanceSummary:
    try:
        return await AttendanceService.get_my_attendance(
            student_id=current_user.user_id,
            threshold=threshold,
            db=db,
        )
    except AttendanceServiceError as e:
        raise _err(e)


@attendance_router.get("/attendance/me/course/{course_id}", response_model=MyCourseAttendanceDetail)
async def get_my_course_attendance(
    course_id:    UUID,
    threshold:    float         = Query(DEFAULT_SHORTAGE_THRESHOLD),
    current_user: CurrentUser   = Depends(require_roles(*_STUDENT)),
    db: AsyncSession            = Depends(get_tenant_db_dep),
) -> MyCourseAttendanceDetail:
    try:
        return await AttendanceService.get_my_course_detail(
            student_id=current_user.user_id,
            course_id=course_id,
            threshold=threshold,
            db=db,
        )
    except AttendanceServiceError as e:
        raise _err(e)
