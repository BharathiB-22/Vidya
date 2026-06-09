"""SIS Validation Report Router — H64.8.

GET /validation/report  — ADMIN / DEAN only
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.validation_schemas import ValidationReportOut
from app.modules.m11_sis.validation_service import ValidationService

validation_router = APIRouter(tags=["SIS Validation"])

_ROLES = (TenantRole.ADMIN, TenantRole.DEAN)


@validation_router.get("/validation/report", response_model=ValidationReportOut)
async def get_validation_report(
    current_user: CurrentUser = Depends(require_roles(*_ROLES)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ValidationReportOut:
    return await ValidationService.generate_report(db=db)
