"""Global Search Router — H64.7.

GET /search?q=<query>  (min 2 chars, max 100)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.modules.m11_sis.search_schemas import SearchResultsOut
from app.modules.m11_sis.search_service import global_search

search_router = APIRouter(tags=["SIS Global Search"])

_ALL_ROLES = (
    TenantRole.ADMIN,
    TenantRole.DEAN,
    TenantRole.FACULTY,
    TenantRole.STUDENT,
)


@search_router.get("/search", response_model=SearchResultsOut)
async def sis_search(
    q: str = Query(..., min_length=2, max_length=100, description="Search query"),
    current_user: CurrentUser = Depends(require_roles(*_ALL_ROLES)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> SearchResultsOut:
    return await global_search(q, actor_role=current_user.role, db=db)
