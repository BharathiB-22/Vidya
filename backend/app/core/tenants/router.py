from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import require_super_admin
from app.core.auth.schemas import CurrentUser
from app.database import get_db
from app.core.tenants.schemas import CreateTenantRequest, DeleteTenantRequest, TenantResponse, TenantUpdateRequest
from app.core.tenants.service import TenantError, TenantService

router = APIRouter(tags=["tenants"])


def _tenant_error(e: TenantError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


@router.post("", response_model=TenantResponse, status_code=201)
async def create_tenant(
    request: Request,
    body: CreateTenantRequest,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    try:
        return await TenantService.create_tenant(
            body,
            db,
            actor_user_id=current_user.user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
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
    request: Request,
    tenant_id: UUID,
    body: TenantUpdateRequest,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    try:
        return await TenantService.update_tenant(
            tenant_id,
            body,
            db,
            actor_user_id=current_user.user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except TenantError as e:
        raise _tenant_error(e)


@router.delete("/{tenant_id}", response_model=TenantResponse)
async def delete_tenant(
    request: Request,
    tenant_id: UUID,
    body: DeleteTenantRequest,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    try:
        return await TenantService.delete_tenant(
            tenant_id,
            body.confirm_slug,
            db,
            actor_user_id=current_user.user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except TenantError as e:
        raise _tenant_error(e)


@router.post("/{tenant_id}/retry", response_model=TenantResponse)
async def retry_tenant_provisioning(
    request: Request,
    tenant_id: UUID,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    try:
        return await TenantService.retry_provisioning(
            tenant_id,
            db,
            actor_user_id=current_user.user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except TenantError as e:
        raise _tenant_error(e)
