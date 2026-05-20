from typing import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.core.auth.dependencies import require_roles
from app.core.auth.models import TenantRole
from app.core.auth.repository import TenantRepository
from app.core.auth.schemas import (
    CreateUserRequest,
    CurrentUser,
    UpdateUserRequest,
    UserResponse,
)
from app.core.auth.service import AuthError, TenantAuthService


async def _get_admin_db(
    current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN)),
) -> AsyncGenerator[AsyncSession, None]:
    # SUPER_ADMIN bypasses require_roles but has no schema_name — reject explicitly.
    # SUPER_ADMIN manages tenants via /tenants/, not /admin/ (tenant-ADMIN routes).
    if current_user.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "FORBIDDEN",
                "message": "SUPER_ADMIN cannot use /admin/ endpoints; use a tenant ADMIN token",
            },
        )
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL search_path = {current_user.schema_name}, public")
            )
            yield session


router = APIRouter(tags=["admin"])


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    request: Request,
    body: CreateUserRequest,
    current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN)),
    db: AsyncSession = Depends(_get_admin_db),
) -> UserResponse:
    try:
        return await TenantAuthService.create_user(
            body,
            current_user.user_id,
            current_user.role,
            current_user.tenant_id,
            current_user.schema_name,
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            db,
        )
    except AuthError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"error": e.code, "message": e.message},
        )


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    db: AsyncSession = Depends(_get_admin_db),
) -> list[UserResponse]:
    users = await TenantRepository.list_users(db)
    return [UserResponse.model_validate(u) for u in users]


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    request: Request,
    user_id: UUID,
    body: UpdateUserRequest,
    current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN)),
    db: AsyncSession = Depends(_get_admin_db),
) -> UserResponse:
    try:
        return await TenantAuthService.update_user(
            user_id, body,
            current_user.user_id,
            current_user.role,
            current_user.tenant_id,
            current_user.schema_name,
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            db,
        )
    except AuthError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"error": e.code, "message": e.message},
        )
