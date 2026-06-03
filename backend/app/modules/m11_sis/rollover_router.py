"""
SIS Semester Rollover — H54 Router.

RBAC: ADMIN only for both endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.rollover_schemas import (
    RolloverCommitResult,
    RolloverPreviewResponse,
    RolloverScopeIn,
)
from app.modules.m11_sis.rollover_service import RolloverService

rollover_router = APIRouter(tags=["M11 SIS Rollover"])

_ADMIN = (TenantRole.ADMIN,)


@rollover_router.post("/rollover/preview", response_model=RolloverPreviewResponse)
async def rollover_preview(
    body: RolloverScopeIn,
    current_user: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> RolloverPreviewResponse:
    return await RolloverService.preview(body, db)


@rollover_router.post("/rollover/commit", response_model=RolloverCommitResult)
async def rollover_commit(
    body: RolloverScopeIn,
    current_user: CurrentUser = Depends(require_roles(*_ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> RolloverCommitResult:
    return await RolloverService.commit(
        body,
        db,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
    )
