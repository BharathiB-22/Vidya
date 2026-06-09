"""Enrollment Capacity Router — H64.6.

GET  /capacity/sections              — list all sections with capacity info (ADMIN/DEAN)
GET  /sections/{id}/capacity         — single section capacity (ADMIN/DEAN/FACULTY)
PUT  /sections/{id}/capacity         — set / clear max_strength (ADMIN)
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.capacity_schemas import SectionCapacityOut, SetCapacityIn
from app.modules.m11_sis.capacity_service import CapacityError, CapacityService

capacity_router = APIRouter(tags=["SIS Enrollment Capacity"])

_ADMIN       = (TenantRole.ADMIN,)
_READ_ROLES  = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)


def _err(e: CapacityError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"error": e.code, "message": e.message})


@capacity_router.get("/capacity/sections", response_model=list[SectionCapacityOut])
async def list_capacity(
    semester_id: Optional[UUID] = Query(None),
    current_user: CurrentUser = Depends(require_roles(*_READ_ROLES)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[SectionCapacityOut]:
    return await CapacityService.list_sections_capacity(semester_id=semester_id, db=db)


@capacity_router.get("/sections/{section_id}/capacity", response_model=SectionCapacityOut)
async def get_capacity(
    section_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_READ_ROLES)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SectionCapacityOut:
    try:
        return await CapacityService.get_section_capacity(section_id, db=db)
    except CapacityError as e:
        raise _err(e)


@capacity_router.put("/sections/{section_id}/capacity", response_model=SectionCapacityOut)
async def set_capacity(
    section_id: UUID,
    body: SetCapacityIn,
    current_user: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SectionCapacityOut:
    try:
        result = await CapacityService.set_capacity(section_id, body.max_strength, db=db)
        await db.commit()
        return result
    except CapacityError as e:
        raise _err(e)
