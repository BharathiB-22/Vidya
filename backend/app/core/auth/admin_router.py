from typing import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
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
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL search_path = {current_user.schema_name}, public")
            )
            yield session


router = APIRouter(tags=["admin"])


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    body: CreateUserRequest,
    db: AsyncSession = Depends(_get_admin_db),
) -> UserResponse:
    try:
        return await TenantAuthService.create_user(body, db)
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
    user_id: UUID,
    body: UpdateUserRequest,
    db: AsyncSession = Depends(_get_admin_db),
) -> UserResponse:
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(
            status_code=422,
            detail={"error": "VALIDATION_ERROR", "message": "No fields to update"},
        )
    user = await TenantRepository.update_user(user_id, updates, db)
    if not user:
        raise HTTPException(
            status_code=404,
            detail={"error": "USER_NOT_FOUND", "message": "User not found"},
        )
    return UserResponse.model_validate(user)
