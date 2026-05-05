import re
from typing import AsyncGenerator, Callable
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from jose import JWTError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.core.auth.models import TenantRole
from app.core.auth.repository import PublicRepository, TenantRepository
from app.core.auth.schemas import CurrentUser, TenantInfo
from app.core.auth.security import decode_token


async def resolve_tenant(
    x_tenant_slug: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> TenantInfo:
    tenant = await PublicRepository.get_tenant_by_slug(x_tenant_slug, db)
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail={"error": "TENANT_NOT_FOUND", "message": "Tenant not found"},
        )
    if not tenant.is_active:
        raise HTTPException(
            status_code=403,
            detail={"error": "TENANT_INACTIVE", "message": "Tenant is inactive"},
        )
    if not re.match(r"^tenant_[a-z0-9_]+$", tenant.schema_name):
        raise HTTPException(
            status_code=500,
            detail={"error": "INTERNAL_ERROR", "message": "Invalid tenant configuration"},
        )
    return TenantInfo(id=tenant.id, slug=tenant.slug, schema_name=tenant.schema_name)


async def get_tenant_db_dep(
    tenant: TenantInfo = Depends(resolve_tenant),
) -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL search_path = {tenant.schema_name}, public")
            )
            yield session


async def get_current_user(
    authorization: str = Header(...),
) -> CurrentUser:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error": "UNAUTHORIZED", "message": "Missing or invalid token"},
        )
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail={"error": "UNAUTHORIZED", "message": "Invalid or expired token"},
        )

    schema_name: str | None = payload.get("schema_name")
    user_id = UUID(payload["sub"])

    if schema_name is None:
        async with AsyncSessionLocal() as db:
            user = await PublicRepository.get_platform_user_by_id(user_id, db)
            if not user or not user.is_active:
                raise HTTPException(
                    status_code=401,
                    detail={"error": "UNAUTHORIZED", "message": "User not found or inactive"},
                )
            return CurrentUser(
                user_id=user.id,
                tenant_id=None,
                schema_name=None,
                role="SUPER_ADMIN",
                email=user.email,
            )
    else:
        if not re.match(r"^tenant_[a-z0-9_]+$", schema_name):
            raise HTTPException(
                status_code=401,
                detail={"error": "UNAUTHORIZED", "message": "Invalid token claims"},
            )
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    text(f"SET LOCAL search_path = {schema_name}, public")
                )
                user = await TenantRepository.get_user_by_id(user_id, session)
                if not user or not user.is_active:
                    raise HTTPException(
                        status_code=401,
                        detail={"error": "UNAUTHORIZED", "message": "User not found or inactive"},
                    )
                tenant_id_str = payload.get("tenant_id")
                return CurrentUser(
                    user_id=user.id,
                    tenant_id=UUID(tenant_id_str) if tenant_id_str else None,
                    schema_name=schema_name,
                    role=user.role.value,
                    email=user.email,
                )


def require_roles(*allowed_roles: TenantRole) -> Callable:
    async def _dependency(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current_user.is_super_admin:
            return current_user
        if current_user.role not in {r.value for r in allowed_roles}:
            raise HTTPException(
                status_code=403,
                detail={"error": "FORBIDDEN", "message": "Insufficient permissions"},
            )
        return current_user

    return _dependency


async def require_super_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    if not current_user.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail={"error": "FORBIDDEN", "message": "Super admin access required"},
        )
    return current_user
