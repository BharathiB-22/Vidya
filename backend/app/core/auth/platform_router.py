from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.core.rate_limiting import limiter
from app.core.auth.dependencies import require_super_admin
from app.core.auth.repository import PublicRepository
from app.core.auth.schemas import (
    CurrentUser,
    GoogleAuthRequest,
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    PasswordResetVerifyIn,
    PlatformBrandingRequest,
    PlatformBrandingResponse,
    PlatformChangePasswordRequest,
    PlatformLoginRequest,
    PlatformMeResponse,
    PlatformSessionsResponse,
    RefreshRequest,
    TokenResponse,
    UpdatePlatformEmailRequest,
    UpdatePlatformProfileRequest,
)
from app.core.auth.service import AuthError, PlatformAuthService
from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.storage.avatar import PLATFORM_SCOPE_SLUG
from app.core.storage.service import StorageError, StorageService

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


@router.post("/google", response_model=TokenResponse)
@limiter.limit("5/minute")
async def platform_google_login(
    request: Request,
    body: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    try:
        return await PlatformAuthService.login_with_google(
            body.credential,
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


@router.get("/me", response_model=PlatformMeResponse)
async def platform_me(
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> PlatformMeResponse:
    user = await PublicRepository.get_platform_user_by_id(current_user.user_id, db)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"error": "UNAUTHORIZED", "message": "User not found"},
        )
    return PlatformMeResponse.model_validate(user)


@router.patch("/me", response_model=PlatformMeResponse)
async def update_platform_profile(
    request: Request,
    body: UpdatePlatformProfileRequest,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> PlatformMeResponse:
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail={"error": "NO_FIELDS", "message": "No fields to update"})
    user = await PublicRepository.update_platform_user(current_user.user_id, updates, db)
    if not user:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "User not found"})
    await db.commit()
    await AuditService.log(
        AuditEventType.PLATFORM_PROFILE_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role="SUPER_ADMIN",
        target_entity="PlatformUser",
        target_id=str(current_user.user_id),
        metadata={"changes": list(updates.keys())},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return PlatformMeResponse.model_validate(user)


@router.post("/me/avatar", response_model=PlatformMeResponse)
async def upload_platform_avatar(
    request: Request,
    file: UploadFile = File(..., description="JPG, JPEG, PNG or WEBP profile picture"),
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> PlatformMeResponse:
    """Upload the super admin's own profile picture.

    Super admins belong to no tenant, so their image lands under the reserved
    `platform` storage prefix rather than a tenant slug. Only the object key is
    persisted; there is no StorageAsset row because that table is tenant-scoped.
    """
    max_bytes = settings.AVATAR_MAX_UPLOAD_SIZE_MB * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "FILE_TOO_LARGE",
                "message": f"Profile picture must be {settings.AVATAR_MAX_UPLOAD_SIZE_MB}MB or smaller.",
            },
        )
    try:
        object_key, _ = await StorageService.upload_avatar(
            owner_id=current_user.user_id,
            scope_slug=PLATFORM_SCOPE_SLUG,
            filename=file.filename,
            content_type=file.content_type,
            data=data,
        )
    except StorageError as e:
        raise HTTPException(status_code=e.status_code, detail={"error": e.code, "message": e.message})

    user = await PublicRepository.update_platform_user(
        current_user.user_id, {"avatar_url": object_key}, db
    )
    if not user:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "User not found"})
    await db.commit()
    await AuditService.log(
        AuditEventType.PLATFORM_PROFILE_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role="SUPER_ADMIN",
        target_entity="PlatformUser",
        target_id=str(current_user.user_id),
        metadata={"changes": ["avatar_url"]},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return PlatformMeResponse.model_validate(user)


@router.delete("/me/avatar", response_model=PlatformMeResponse)
async def delete_platform_avatar(
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> PlatformMeResponse:
    user = await PublicRepository.update_platform_user(
        current_user.user_id, {"avatar_url": None}, db
    )
    if not user:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "User not found"})
    await db.commit()
    return PlatformMeResponse.model_validate(user)


@router.patch("/me/email", response_model=PlatformMeResponse)
async def update_platform_email(
    request: Request,
    body: UpdatePlatformEmailRequest,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> PlatformMeResponse:
    from app.core.auth.security import verify_password
    user = await PublicRepository.get_platform_user_by_id(current_user.user_id, db)
    if not user:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "User not found"})
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail={"error": "INVALID_CREDENTIALS", "message": "Current password is incorrect"})
    existing = await PublicRepository.get_platform_user_by_email(str(body.new_email), db)
    if existing and existing.id != current_user.user_id:
        raise HTTPException(status_code=409, detail={"error": "EMAIL_EXISTS", "message": "Email is already in use"})
    old_email = user.email
    user = await PublicRepository.update_platform_user(current_user.user_id, {"email": str(body.new_email)}, db)
    await db.commit()
    await AuditService.log(
        AuditEventType.PLATFORM_EMAIL_CHANGED,
        actor_user_id=current_user.user_id,
        actor_role="SUPER_ADMIN",
        target_entity="PlatformUser",
        target_id=str(current_user.user_id),
        metadata={"old_email": old_email, "new_email": str(body.new_email)},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return PlatformMeResponse.model_validate(user)


@router.patch("/me/password", status_code=200)
async def change_platform_password(
    request: Request,
    body: PlatformChangePasswordRequest,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from datetime import datetime, timezone
    from app.core.auth.security import hash_password, verify_password
    user = await PublicRepository.get_platform_user_by_id(current_user.user_id, db)
    if not user:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "User not found"})
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail={"error": "INVALID_CREDENTIALS", "message": "Current password is incorrect"})
    new_hash = hash_password(body.new_password)
    await PublicRepository.update_platform_user(
        current_user.user_id,
        {"password_hash": new_hash, "password_changed_at": datetime.now(timezone.utc)},
        db,
    )
    await PublicRepository.revoke_all_platform_user_refresh_tokens(current_user.user_id, db)
    await db.commit()
    await AuditService.log(
        AuditEventType.PLATFORM_PASSWORD_CHANGED,
        actor_user_id=current_user.user_id,
        actor_role="SUPER_ADMIN",
        target_entity="PlatformUser",
        target_id=str(current_user.user_id),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"message": "Password changed successfully. All other sessions have been terminated."}


@router.get("/me/sessions", response_model=PlatformSessionsResponse)
async def get_platform_sessions(
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> PlatformSessionsResponse:
    user = await PublicRepository.get_platform_user_by_id(current_user.user_id, db)
    active_count = await PublicRepository.count_active_platform_sessions(current_user.user_id, db)
    return PlatformSessionsResponse(
        active_session_count=active_count,
        last_login_at=user.last_login_at if user else None,
    )


@router.get("/branding", response_model=PlatformBrandingResponse)
async def get_platform_branding(
    db: AsyncSession = Depends(get_db),
) -> PlatformBrandingResponse:
    branding = await PublicRepository.get_platform_branding(db)
    if branding is None:
        from app.core.auth.models import PlatformBranding
        branding = PlatformBranding(platform_name="VIDYA AI", company_name="SherpaVector")
    return PlatformBrandingResponse.model_validate(branding)


@router.patch("/branding", response_model=PlatformBrandingResponse)
async def update_platform_branding(
    request: Request,
    body: PlatformBrandingRequest,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> PlatformBrandingResponse:
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail={"error": "NO_FIELDS", "message": "No fields to update"})
    branding = await PublicRepository.upsert_platform_branding(updates, db)
    await db.commit()
    await AuditService.log(
        AuditEventType.PLATFORM_BRANDING_UPDATED,
        actor_user_id=current_user.user_id,
        actor_role="SUPER_ADMIN",
        target_entity="PlatformBranding",
        target_id=str(branding.id),
        metadata={"changes": list(updates.keys())},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return PlatformBrandingResponse.model_validate(branding)


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
