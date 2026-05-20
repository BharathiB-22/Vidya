from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.core.rate_limiting import limiter
from app.core.auth.dependencies import (
    get_current_user,
    get_tenant_db_dep,
    resolve_tenant,
)
from app.core.auth.repository import TenantRepository
from app.core.auth.schemas import (
    LoginRequest,
    MeResponse,
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    PasswordResetVerifyIn,
    RefreshRequest,
    TenantInfo,
    TokenResponse,
    CurrentUser,
)
from app.core.auth.service import AuthError, TenantAuthService

router = APIRouter(tags=["auth"])


def _auth_error(e: AuthError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def tenant_login(
    request: Request,
    body: LoginRequest,
    tenant: TenantInfo = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> TokenResponse:
    try:
        return await TenantAuthService.login(
            body.email,
            body.password,
            tenant.id,
            tenant.schema_name,
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            db,
        )
    except AuthError as e:
        raise _auth_error(e)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh_tokens(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    try:
        return await TenantAuthService.refresh_tokens(
            body.refresh_token,
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            db,
        )
    except AuthError as e:
        raise _auth_error(e)


@router.post("/logout", status_code=200)
async def logout(
    request: Request,
    body: RefreshRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await TenantAuthService.logout(
            body.refresh_token,
            current_user.user_id,
            current_user.role,
            current_user.tenant_id,
            current_user.schema_name,
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            db,
        )
    except AuthError as e:
        raise _auth_error(e)
    return {"message": "Logged out"}


@router.post("/logout-all", status_code=200)
async def logout_all(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        if current_user.is_super_admin:
            from app.core.auth.service import PlatformAuthService
            await PlatformAuthService.logout_all(
                current_user.user_id,
                request.client.host if request.client else None,
                request.headers.get("user-agent"),
                db,
            )
        else:
            await TenantAuthService.logout_all(
                current_user.user_id,
                current_user.role,
                current_user.tenant_id,
                current_user.schema_name,
                request.client.host if request.client else None,
                request.headers.get("user-agent"),
                db,
            )
    except AuthError as e:
        raise _auth_error(e)
    return {"message": "All sessions terminated"}


@router.get("/me", response_model=MeResponse)
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
) -> MeResponse:
    if current_user.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail={"error": "FORBIDDEN", "message": "Use /platform/auth/me for super admin"},
        )
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text(f"SET LOCAL search_path = {current_user.schema_name}, public")
            )
            user = await TenantRepository.get_user_by_id(current_user.user_id, session)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"error": "UNAUTHORIZED", "message": "User not found"},
        )
    return MeResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        full_name=user.full_name,
        identifier=user.identifier,
        is_active=user.is_active,
        created_at=user.created_at,
        tenant_id=current_user.tenant_id,
        schema_name=current_user.schema_name,
    )


@router.post("/password-reset/request", status_code=200)
@limiter.limit("3/15minute")
async def request_reset(
    request: Request,
    body: PasswordResetRequestIn,
    tenant: TenantInfo = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    await TenantAuthService.request_password_reset(
        body.email,
        tenant.id,
        tenant.schema_name,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
        db,
    )
    return {"message": "If that email exists, an OTP has been sent"}


@router.post("/password-reset/verify", status_code=200)
async def verify_otp(
    request: Request,
    body: PasswordResetVerifyIn,
    tenant: TenantInfo = Depends(resolve_tenant),
    db: AsyncSession = Depends(get_tenant_db_dep),
):
    try:
        return await TenantAuthService.verify_otp_and_issue_reset_token(
            body.email, body.otp,
            tenant.schema_name,
            tenant.id,
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            db,
        )
    except AuthError as e:
        raise _auth_error(e)


@router.post("/password-reset/confirm", status_code=200)
async def confirm_reset(
    request: Request,
    body: PasswordResetConfirmIn,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await TenantAuthService.confirm_password_reset(
            body.reset_token, body.new_password,
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            db,
        )
    except AuthError as e:
        raise _auth_error(e)
    return {"message": "Password reset successful"}
