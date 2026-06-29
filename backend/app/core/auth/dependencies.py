import re
from typing import AsyncGenerator, Callable, Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from jose import JWTError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, _tenant_schema_ctx, get_db
from app.core.auth.models import TenantRole
from app.core.auth.repository import PublicRepository, TenantRepository
from app.core.auth.schemas import CurrentUser, TenantInfo
from app.core.auth.security import decode_token


async def resolve_tenant(
    x_tenant_slug: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> TenantInfo:
    # Reject slugs with null bytes or ASCII control characters before hitting the DB.
    # asyncpg raises CharacterNotInRepertoireError for 0x00, which becomes an unhandled 500.
    if any(ord(c) < 32 for c in x_tenant_slug):
        raise HTTPException(
            status_code=404,
            detail={"error": "TENANT_NOT_FOUND", "message": "Tenant not found"},
        )
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


async def get_current_user(
    authorization: Optional[str] = Header(None),
) -> CurrentUser:
    if authorization is None or not authorization.startswith("Bearer "):
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
    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=401,
            detail={"error": "UNAUTHORIZED", "message": "Invalid token claims"},
        )

    if schema_name is None:
        # Defensive: clear any tenant schema context that may have leaked from a
        # prior request in the same asyncio task (e.g., test suites sharing a loop).
        # Without this, the engine "begin" event would inject SET LOCAL search_path
        # to a dropped tenant schema, causing "relation 'users' does not exist".
        _ctx_token = _tenant_schema_ctx.set(None)
        try:
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
        finally:
            _tenant_schema_ctx.reset(_ctx_token)
    else:
        if not re.match(r"^tenant_[a-z0-9_]+$", schema_name):
            raise HTTPException(
                status_code=401,
                detail={"error": "UNAUTHORIZED", "message": "Invalid token claims"},
            )
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await session.execute(
                        text(f"SET LOCAL search_path = {schema_name}, public")
                    )
                    user = await TenantRepository.get_user_by_id(user_id, session)
        except SQLAlchemyError:
            # Schema doesn't exist or users table not found — treat as user not found.
            raise HTTPException(
                status_code=401,
                detail={"error": "UNAUTHORIZED", "message": "User not found or inactive"},
            )
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


async def verify_tenant_match(
    current_user: CurrentUser = Depends(get_current_user),
    tenant: TenantInfo = Depends(resolve_tenant),
) -> None:
    """Verify the JWT's schema_name matches the tenant resolved from X-Tenant-Slug.

    SUPER_ADMIN philosophy:
      - Platform-scoped by default (schema_name=None in JWT).
      - May access tenant data only with an explicit, valid X-Tenant-Slug header
        (already enforced by resolve_tenant).
      - Never falls back silently to the public schema.

    For all other users the JWT schema_name must exactly equal the resolved
    tenant's schema_name. Any mismatch is a cross-tenant access attempt and
    fails hard with 403 — no partial context is returned.
    """
    if current_user.is_super_admin:
        return
    if current_user.schema_name != tenant.schema_name:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "TENANT_MISMATCH",
                "message": "Token tenant does not match requested tenant context",
            },
        )


async def get_tenant_db_dep(
    tenant: TenantInfo = Depends(resolve_tenant),
    _: None = Depends(verify_tenant_match),
) -> AsyncGenerator[AsyncSession, None]:
    # Set the per-request ContextVar so the engine "begin" event injects
    # SET LOCAL search_path at the start of EVERY transaction on this session.
    # This is the only correct pattern for PgBouncer transaction pooling mode:
    # after each COMMIT the backend connection is recycled and a new BEGIN may
    # land on a different backend with search_path = public.
    token = _tenant_schema_ctx.set(tenant.schema_name)
    try:
        async with AsyncSessionLocal() as session:
            yield session
    finally:
        _tenant_schema_ctx.reset(token)


async def get_tenant_context_dep(
    tenant: TenantInfo = Depends(resolve_tenant),
    _: None = Depends(verify_tenant_match),
) -> AsyncGenerator[dict, None]:
    """Yields {"db", "schema_name", "tenant_id"} for modules that need all three."""
    token = _tenant_schema_ctx.set(tenant.schema_name)
    try:
        async with AsyncSessionLocal() as session:
            yield {"db": session, "schema_name": tenant.schema_name, "tenant_id": tenant.id}
    finally:
        _tenant_schema_ctx.reset(token)


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


# ---------------------------------------------------------------------------
# Faculty responsibility grants (ERP Onboarding Phase 1.5)
#
# A single FACULTY account may hold multiple active responsibilities (GUIDE /
# EVALUATOR / BOARD / DEAN) via faculty_role_grants — no separate accounts.
# Visibility/access for those responsibilities is driven by active grants, not
# by a hardcoded users.role check.
# ---------------------------------------------------------------------------

async def user_active_grants(user_id: UUID, schema_name: str | None) -> set[str]:
    """Active responsibility role_codes held by a user (own session, tenant-scoped)."""
    if not schema_name or not re.match(r"^tenant_[a-z0-9_]+$", schema_name):
        return set()
    _ctx = _tenant_schema_ctx.set(None)
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(text(f"SET LOCAL search_path = {schema_name}, public"))
                res = await session.execute(
                    text(
                        "SELECT role_code FROM faculty_role_grants "
                        "WHERE faculty_user_id = :u AND is_active = true"
                    ),
                    {"u": str(user_id)},
                )
                return {r[0] for r in res.fetchall()}
    except SQLAlchemyError:
        return set()
    finally:
        _tenant_schema_ctx.reset(_ctx)


async def user_has_grant(db: AsyncSession, user_id: UUID, role_code: str) -> bool:
    """True if ``user_id`` holds an active grant for ``role_code``.

    Uses the caller's session (search_path already set) — for use inside services.
    """
    res = await db.execute(
        text(
            "SELECT 1 FROM faculty_role_grants "
            "WHERE faculty_user_id = :u AND role_code = :r AND is_active = true LIMIT 1"
        ),
        {"u": str(user_id), "r": role_code.upper()},
    )
    return res.first() is not None


def require_responsibility(*allowed: "TenantRole | str") -> Callable:
    """Pass if the user holds one of ``allowed`` as a base role OR an active grant.

    Any role may hold responsibilities via grants — a FACULTY user with a GUIDE
    grant, or a DEAN with a FACULTY grant for teaching duties, both pass.
    """
    allowed_codes = {a.value if isinstance(a, TenantRole) else str(a).upper() for a in allowed}

    async def _dependency(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current_user.is_super_admin:
            return current_user
        if current_user.role in allowed_codes:
            return current_user
        grants = await user_active_grants(current_user.user_id, current_user.schema_name)
        if grants & allowed_codes:
            return current_user
        raise HTTPException(
            status_code=403,
            detail={"error": "FORBIDDEN", "message": "Insufficient permissions"},
        )

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
