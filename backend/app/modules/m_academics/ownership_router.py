"""Academic Ownership & Responsibility — router (Phase B).

RBAC
----
  FACULTY, DEAN → GET /faculty/me/responsibilities, /faculty/me/summary
  DEAN, ADMIN   → GET /dean/programs, /dean/faculty-assignments, /dean/faculty-workload
                   POST /dean/assign-faculty
                   DELETE /dean/remove-faculty/{id}
                   GET /ownership-matrix

ADMIN always passes all DEAN checks.
Dean scope enforcement (program-level) is in OwnershipService, not here.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m_academics.ownership_schemas import (
    DeanProgramOut,
    DeanProgramsSet,
    DeptInfo,
    FacultyAcademicResponsibilities,
    FacultyAcademicSummary,
    FacultyProgramAssignCreate,
    FacultyProgramAssignOut,
    FacultyWorkloadItem,
    FacultyWorkloadResponse,
    OwnershipDashboardSummary,
    OwnershipMatrixOut,
)
from app.modules.m_academics.ownership_service import OwnershipService, OwnershipServiceError

ownership_router = APIRouter(tags=["academic-ownership"])

_FACULTY = (TenantRole.FACULTY, TenantRole.DEAN, TenantRole.ADMIN)
_MANAGE  = (TenantRole.DEAN,    TenantRole.ADMIN)


def _err(e: OwnershipServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


# ---------------------------------------------------------------------------
# Faculty self-service — responsibilities
# ---------------------------------------------------------------------------

@ownership_router.get(
    "/faculty/me/responsibilities",
    response_model=FacultyAcademicResponsibilities,
)
async def get_my_responsibilities(
    current_user: CurrentUser = Depends(require_roles(*_FACULTY)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> FacultyAcademicResponsibilities:
    """Return the full academic scope for the signed-in faculty or dean."""
    try:
        return await OwnershipService.get_faculty_responsibilities(
            current_user.user_id, db=db
        )
    except OwnershipServiceError as e:
        raise _err(e)


@ownership_router.get(
    "/faculty/me/summary",
    response_model=FacultyAcademicSummary,
)
async def get_my_summary(
    current_user: CurrentUser = Depends(require_roles(*_FACULTY)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> FacultyAcademicSummary:
    """Quick stats for the faculty dashboard banner."""
    try:
        return await OwnershipService.get_faculty_summary(
            current_user.user_id, db=db
        )
    except OwnershipServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Dean / Admin — governed programs
# ---------------------------------------------------------------------------

@ownership_router.get(
    "/dean/programs",
    response_model=list[DeanProgramOut],
)
async def get_dean_programs(
    current_user: CurrentUser = Depends(require_roles(*_MANAGE)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> list[DeanProgramOut]:
    """Programs the calling dean governs (ADMIN sees all programs)."""
    try:
        if current_user.role == "ADMIN":
            rows = (
                await db.execute(
                    text(
                        "SELECT ap.id, ap.name, ap.code, ap.degree_type, "
                        "       d.id AS dept_id, d.name AS dept_name, d.code AS dept_code, "
                        "       (SELECT COUNT(*) FROM faculty_program_assignments fpa "
                        "        WHERE fpa.program_id = ap.id AND fpa.is_active = true) AS active_faculty "
                        "FROM   acad_programs ap "
                        "LEFT   JOIN acad_departments d ON d.id = ap.department_id "
                        "WHERE  ap.is_active = true "
                        "ORDER  BY ap.name"
                    )
                )
            ).mappings().all()
            return [
                DeanProgramOut(
                    id=r["id"],
                    name=r["name"],
                    code=r["code"],
                    degree_type=r["degree_type"],
                    department=(
                        DeptInfo(id=r["dept_id"], name=r["dept_name"], code=r["dept_code"])
                        if r["dept_id"] else None
                    ),
                    active_faculty_count=r["active_faculty"] or 0,
                )
                for r in rows
            ]
        return await OwnershipService.get_dean_programs(current_user.user_id, db=db)
    except OwnershipServiceError as e:
        raise _err(e)


@ownership_router.get(
    "/dean/faculty-assignments",
    response_model=list[FacultyProgramAssignOut],
)
async def list_dean_faculty_assignments(
    current_user: CurrentUser = Depends(require_roles(*_MANAGE)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> list[FacultyProgramAssignOut]:
    """All active faculty-program assignments under the dean's governed programs."""
    try:
        return await OwnershipService.list_dean_faculty_assignments(
            current_user.user_id,
            actor_role=current_user.role,
            db=db,
        )
    except OwnershipServiceError as e:
        raise _err(e)


@ownership_router.get(
    "/dean/faculty-workload",
    response_model=FacultyWorkloadResponse,
)
async def get_faculty_workload(
    current_user: CurrentUser = Depends(require_roles(*_MANAGE)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> FacultyWorkloadResponse:
    """Course + program count per faculty in the dean's governed programs."""
    try:
        if current_user.role == "ADMIN":
            rows = (
                await db.execute(
                    text(
                        "SELECT fpa.faculty_user_id, "
                        "       COUNT(DISTINCT fpa.program_id) AS program_count, "
                        "       (SELECT COUNT(*) FROM subject_assignments sa "
                        "        WHERE sa.faculty_user_id = fpa.faculty_user_id "
                        "          AND sa.is_active = true) AS course_count "
                        "FROM   faculty_program_assignments fpa "
                        "WHERE  fpa.is_active = true "
                        "GROUP  BY fpa.faculty_user_id"
                    )
                )
            ).mappings().all()
            return FacultyWorkloadResponse(
                items=[
                    FacultyWorkloadItem(
                        faculty_user_id=r["faculty_user_id"],
                        course_count=r["course_count"] or 0,
                        program_count=r["program_count"] or 0,
                    )
                    for r in rows
                ]
            )
        dean_programs = await OwnershipService.get_dean_programs(current_user.user_id, db=db)
        program_ids = [p.id for p in dean_programs]
        return await OwnershipService.get_faculty_workload(program_ids, db=db)
    except OwnershipServiceError as e:
        raise _err(e)


@ownership_router.post(
    "/dean/assign-faculty",
    response_model=FacultyProgramAssignOut,
    status_code=201,
)
async def assign_faculty_to_program(
    body: FacultyProgramAssignCreate,
    current_user: CurrentUser = Depends(require_roles(*_MANAGE)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> FacultyProgramAssignOut:
    """Assign a faculty member to a program scope. Dean-scope enforced for DEAN actors."""
    try:
        return await OwnershipService.assign_faculty_to_program(
            body,
            assigned_by=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except OwnershipServiceError as e:
        raise _err(e)


@ownership_router.delete(
    "/dean/remove-faculty/{assignment_id}",
    response_model=FacultyProgramAssignOut,
)
async def remove_faculty_from_program(
    assignment_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_MANAGE)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> FacultyProgramAssignOut:
    """Soft-revoke a faculty-program assignment. Dean-scope enforced for DEAN actors."""
    try:
        return await OwnershipService.remove_faculty_from_program(
            assignment_id,
            revoked_by=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except OwnershipServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Dean governance — WHICH programmes a Dean governs
#
# ADMIN only, and deliberately not _MANAGE (which includes DEAN). A Dean must not be
# able to widen his own governance, or the scope that every other check in this system
# rests on — his curriculum, his faculty, his students, his timetable — would be a scope
# he grants himself.
#
# The table and every read of it have existed since Phase B. The WRITE did not: the only
# rows in any tenant came from a one-off backfill migration, so a Dean created afterwards
# governed nothing and no screen could give him anything. This is the missing act, and
# nothing about the ownership model changes.
# ---------------------------------------------------------------------------

@ownership_router.get(
    "/deans/{dean_user_id}/programs",
    response_model=list[UUID],
)
async def list_programs_governed_by_dean(
    dean_user_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> list[UUID]:
    """The programmes this Dean governs — the ids the Admin's editor starts from."""
    try:
        return await OwnershipService.list_dean_programs(dean_user_id, db=db)
    except OwnershipServiceError as e:
        raise _err(e)


@ownership_router.put(
    "/deans/{dean_user_id}/programs",
    response_model=list[UUID],
)
async def set_programs_governed_by_dean(
    dean_user_id: UUID,
    body: DeanProgramsSet,
    current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> list[UUID]:
    """Set the whole list of programmes a Dean governs.

    Declarative: the Admin sends the list that should be true, and it becomes true.
    Programmes removed are soft-revoked, never deleted — governance is a matter of
    record, and somebody will eventually ask who oversaw what, and when.
    """
    try:
        return await OwnershipService.set_dean_programs(
            dean_user_id,
            body.program_ids,
            assigned_by=current_user.user_id,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            db=db,
        )
    except OwnershipServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------

@ownership_router.get(
    "/dean/dashboard-summary",
    response_model=OwnershipDashboardSummary,
)
async def get_dashboard_summary(
    current_user: CurrentUser = Depends(require_roles(*_MANAGE)),
    db: AsyncSession          = Depends(get_tenant_db_dep),
) -> OwnershipDashboardSummary:
    """Totals + vacancy + workload for the Academic Ownership dashboard tab.

    DEAN sees only governed programs; ADMIN sees all. Every figure is
    derived from existing assignment/program data — no new pending state.
    """
    try:
        return await OwnershipService.get_dashboard_summary(
            current_user.user_id, actor_role=current_user.role, db=db
        )
    except OwnershipServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Ownership matrix
# ---------------------------------------------------------------------------

@ownership_router.get(
    "/ownership-matrix",
    response_model=OwnershipMatrixOut,
)
async def get_ownership_matrix(
    program_ids: str | None    = Query(None, description="Comma-separated program UUIDs to filter"),
    current_user: CurrentUser  = Depends(require_roles(*_MANAGE)),
    db: AsyncSession           = Depends(get_tenant_db_dep),
) -> OwnershipMatrixOut:
    """Program → Semester → Course → Faculty matrix.

    DEAN sees only programs they govern.
    ADMIN sees all (or filtered via ?program_ids=uuid1,uuid2).
    """
    try:
        if current_user.role == "ADMIN":
            if program_ids:
                pids = [UUID(p.strip()) for p in program_ids.split(",") if p.strip()]
            else:
                rows = (await db.execute(text("SELECT id FROM acad_programs WHERE is_active = true"))).scalars().all()
                pids = list(rows)
        else:
            dean_programs = await OwnershipService.get_dean_programs(
                current_user.user_id, db=db
            )
            if program_ids:
                filter_ids = {p.strip() for p in program_ids.split(",")}
                pids = [p.id for p in dean_programs if str(p.id) in filter_ids]
            else:
                pids = [p.id for p in dean_programs]

        return await OwnershipService.get_ownership_matrix(pids, db=db)
    except OwnershipServiceError as e:
        raise _err(e)
