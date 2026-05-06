from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import require_super_admin
from app.core.auth.schemas import CurrentUser
from app.database import get_db
from app.core.tenants.schemas import CreateTenantRequest, TenantResponse, TenantUpdateRequest
from app.core.tenants.service import TenantError, TenantService

router = APIRouter(tags=["tenants"])


def _tenant_error(e: TenantError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


@router.post("", response_model=TenantResponse, status_code=201)
async def create_tenant(
    body: CreateTenantRequest,
    _: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    try:
        return await TenantService.create_tenant(body, db)
    except TenantError as e:
        raise _tenant_error(e)


@router.get("", response_model=list[TenantResponse])
async def list_tenants(
    include_inactive: bool = True,
    _: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> list[TenantResponse]:
    return await TenantService.list_tenants(db, include_inactive=include_inactive)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: UUID,
    _: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    try:
        return await TenantService.get_tenant(tenant_id, db)
    except TenantError as e:
        raise _tenant_error(e)


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: UUID,
    body: TenantUpdateRequest,
    _: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    try:
        return await TenantService.update_tenant(tenant_id, body, db)
    except TenantError as e:
        raise _tenant_error(e)
