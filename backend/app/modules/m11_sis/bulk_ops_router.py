"""SIS Bulk Operations Router — H64.5.

POST /students/bulk   — bulk DEACTIVATE or ARCHIVE students  (ADMIN only)
POST /faculty/bulk    — bulk DEACTIVATE or ARCHIVE faculty    (ADMIN only)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.bulk_ops_schemas import BulkFacultyIn, BulkOpResult, BulkStudentIn
from app.modules.m11_sis.bulk_ops_service import BulkOpsService

bulk_ops_router = APIRouter(tags=["SIS Bulk Operations"])

_ADMIN = (TenantRole.ADMIN,)


@bulk_ops_router.post("/students/bulk", response_model=BulkOpResult)
async def bulk_student_action(
    body: BulkStudentIn,
    current_user: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> BulkOpResult:
    """ADMIN-only human gate: apply a lifecycle action to multiple students."""
    return await BulkOpsService.bulk_student_action(
        body.student_ids,
        body.action,
        reason=body.reason,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        db=db,
    )


@bulk_ops_router.post("/faculty/bulk", response_model=BulkOpResult)
async def bulk_faculty_action(
    body: BulkFacultyIn,
    current_user: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> BulkOpResult:
    """ADMIN-only human gate: apply a lifecycle action to multiple faculty."""
    return await BulkOpsService.bulk_faculty_action(
        body.faculty_ids,
        body.action,
        reason=body.reason,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        db=db,
    )
