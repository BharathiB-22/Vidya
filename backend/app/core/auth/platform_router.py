from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.rate_limiting import limiter
from app.core.auth.dependencies import require_super_admin
from app.core.auth.repository import PublicRepository
from app.core.auth.schemas import (
    CurrentUser,
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    PasswordResetVerifyIn,
    PlatformLoginRequest,
    RefreshRequest,
    TokenResponse,
)
from app.core.auth.service import AuthError, PlatformAuthService

router = APIRouter(tags=["platform-auth"])


def _auth_error(e: AuthError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def platform_login(
    request: Request,
    body: PlatformLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    try:
        return await PlatformAuthService.login(
            body.email,
            body.password,
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            db,
        )
    except AuthError as e:
        raise _auth_error(e)


@router.post("/refresh", response_model=TokenResponse)
async def platform_refresh(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    try:
        return await PlatformAuthService.refresh_tokens(
            body.refresh_token,
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            db,
        )
    except AuthError as e:
        raise _auth_error(e)


@router.post("/logout", status_code=200)
async def platform_logout(
    request: Request,
    body: RefreshRequest,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await PlatformAuthService.logout(
            body.refresh_token,
            current_user.user_id,
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            db,
        )
    except AuthError as e:
        raise _auth_error(e)
    return {"message": "Logged out"}


@router.post("/logout-all", status_code=200)
async def platform_logout_all(
    request: Request,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await PlatformAuthService.logout_all(
            current_user.user_id,
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            db,
        )
    except AuthError as e:
        raise _auth_error(e)
    return {"message": "All sessions terminated"}


@router.get("/me")
async def platform_me(
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await PublicRepository.get_platform_user_by_id(current_user.user_id, db)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"error": "UNAUTHORIZED", "message": "User not found"},
        )
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": "SUPER_ADMIN",
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


@router.post("/password-reset/request", status_code=200)
async def platform_request_reset(
    request: Request,
    body: PasswordResetRequestIn,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await PlatformAuthService.request_password_reset(
        body.email,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
        db,
    )
    return {"message": "If that email exists, an OTP has been sent"}


@router.post("/password-reset/verify", status_code=200)
async def platform_verify_otp(
    request: Request,
    body: PasswordResetVerifyIn,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await PlatformAuthService.verify_otp_and_issue_reset_token(
            body.email, body.otp,
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            db,
        )
    except AuthError as e:
        raise _auth_error(e)


@router.post("/password-reset/confirm", status_code=200)
async def platform_confirm_reset(
    request: Request,
    body: PasswordResetConfirmIn,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await PlatformAuthService.confirm_password_reset(
            body.reset_token, body.new_password,
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            db,
        )
    except AuthError as e:
        raise _auth_error(e)
    return {"message": "Password reset successful"}
