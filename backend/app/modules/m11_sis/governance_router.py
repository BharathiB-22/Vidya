"""Governance Directory router — P1.9A.

Read-only endpoints listing academic leadership (Deans) and examination
governance (Board Members).  No editing; informational only.

Routes:
  GET /sis/governance/deans   — all active DEAN users with profile info
  GET /sis/governance/board   — all active BOARD users with profile info
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.governance_schemas import (
    DeptInfo,
    GovernanceBoardItem,
    GovernanceBoardListResponse,
    GovernanceDeanItem,
    GovernanceDeanListResponse,
)

governance_router = APIRouter(tags=["M11 SIS Governance"])

_READ = (TenantRole.ADMIN,)

_DEAN_SQL = text(
    """
    SELECT u.id          AS user_id,
           u.full_name,
           u.email,
           u.is_active,
           p.designation,
           d.id          AS dept_id,
           d.name        AS dept_name,
           d.code        AS dept_code
    FROM   users u
    LEFT   JOIN sis_faculty_profiles p ON p.user_id = u.id
    LEFT   JOIN acad_departments     d ON d.id = p.primary_department_id
    WHERE  u.role = CAST('DEAN' AS tenantrole)
    ORDER  BY u.full_name
    """
)

_BOARD_SQL = text(
    """
    SELECT u.id          AS user_id,
           u.full_name,
           u.email,
           u.is_active,
           p.designation,
           d.id          AS dept_id,
           d.name        AS dept_name,
           d.code        AS dept_code
    FROM   users u
    LEFT   JOIN sis_faculty_profiles p ON p.user_id = u.id
    LEFT   JOIN acad_departments     d ON d.id = p.primary_department_id
    WHERE  u.role = CAST('BOARD' AS tenantrole)
    ORDER  BY u.full_name
    """
)

_DEAN_GRANTS_SQL = text(
    """
    SELECT faculty_user_id::text AS uid, role_code
    FROM   faculty_role_grants
    WHERE  faculty_user_id = ANY(:ids) AND is_active = true
    """
)


@governance_router.get("/governance/deans", response_model=GovernanceDeanListResponse)
async def list_governance_deans(
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> GovernanceDeanListResponse:
    rows = (await db.execute(_DEAN_SQL)).mappings().all()

    # Fetch active grants for all deans in one query.
    dean_ids = [str(r["user_id"]) for r in rows]
    grants_map: dict[str, list[str]] = {}
    if dean_ids:
        grant_rows = (
            await db.execute(_DEAN_GRANTS_SQL, {"ids": dean_ids})
        ).fetchall()
        for uid, code in grant_rows:
            grants_map.setdefault(uid, []).append(code)

    items: list[GovernanceDeanItem] = []
    for r in rows:
        dept = (
            DeptInfo(id=r["dept_id"], name=r["dept_name"], code=r["dept_code"])
            if r["dept_id"]
            else None
        )
        resps = sorted(grants_map.get(str(r["user_id"]), []))
        items.append(
            GovernanceDeanItem(
                user_id=r["user_id"],
                full_name=r["full_name"],
                email=r["email"],
                designation=r["designation"],
                department=dept,
                responsibilities=resps,
                is_active=r["is_active"],
            )
        )
    return GovernanceDeanListResponse(total=len(items), items=items)


@governance_router.get("/governance/board", response_model=GovernanceBoardListResponse)
async def list_governance_board(
    current_user: CurrentUser = Depends(require_roles(*_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> GovernanceBoardListResponse:
    rows = (await db.execute(_BOARD_SQL)).mappings().all()
    items: list[GovernanceBoardItem] = []
    for r in rows:
        dept = (
            DeptInfo(id=r["dept_id"], name=r["dept_name"], code=r["dept_code"])
            if r["dept_id"]
            else None
        )
        items.append(
            GovernanceBoardItem(
                user_id=r["user_id"],
                full_name=r["full_name"],
                email=r["email"],
                designation=r["designation"],
                department=dept,
                is_active=r["is_active"],
            )
        )
    return GovernanceBoardListResponse(total=len(items), items=items)
