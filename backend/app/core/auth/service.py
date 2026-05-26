import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import AsyncSessionLocal
from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.models import OTPPurpose
from app.core.auth.repository import PublicRepository, TenantRepository
from app.core.auth.schemas import (
    CreateUserRequest,
    PasswordResetTokenResponse,
    TokenResponse,
    UpdateUserRequest,
    UserResponse,
)
from app.core.auth.security import (
    create_access_token,
    create_reset_token,
    decode_token,
    generate_otp,
    generate_refresh_token,
    hash_otp,
    hash_password,
    hash_token,
    verify_otp,
    verify_password,
)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class AuthError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 401):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@asynccontextmanager
async def _open_tenant_session(schema_name: str):
    if not re.match(r"^tenant_[a-z0-9_]+$", schema_name):
        raise AuthError("INTERNAL_ERROR", "Invalid schema_name", 500)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {schema_name}, public"))
            yield session


# ---------------------------------------------------------------------------
# SUPER_ADMIN auth flows (public schema)
# ---------------------------------------------------------------------------

class PlatformAuthService:

    @staticmethod
    async def login(
        email: str,
        password: str,
        ip: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> TokenResponse:
        user = await PublicRepository.get_platform_user_by_email(email, db)
        if not user or not user.is_active:
            await AuditService.log(
                AuditEventType.PLATFORM_LOGIN_FAILURE,
                metadata={"attempted_email": email},
                ip_address=ip, user_agent=user_agent,
            )
            raise AuthError("INVALID_CREDENTIALS", "Invalid credentials")
        if not verify_password(password, user.password_hash):
            await AuditService.log(
                AuditEventType.PLATFORM_LOGIN_FAILURE,
                metadata={"attempted_email": email},
                ip_address=ip, user_agent=user_agent,
            )
            raise AuthError("INVALID_CREDENTIALS", "Invalid credentials")

        expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            {
                "sub": str(user.id),
                "tenant_id": None,
                "schema_name": None,
                "role": "SUPER_ADMIN",
                "email": user.email,
            },
            expires_delta=expires,
        )
        raw_refresh = generate_refresh_token()
        token_hash = hash_token(raw_refresh)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        await PublicRepository.create_platform_refresh_token(
            user.id, token_hash, expires_at, ip, user_agent, db
        )
        await PublicRepository.update_platform_user(
            user.id, {"last_login_at": datetime.now(timezone.utc)}, db
        )
        await db.commit()
        await AuditService.log(
            AuditEventType.PLATFORM_LOGIN_SUCCESS,
            actor_user_id=user.id, actor_role="SUPER_ADMIN",
            ip_address=ip, user_agent=user_agent,
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            expires_in=int(expires.total_seconds()),
        )

    @staticmethod
    async def login_with_google(
        google_credential: str,
        ip: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> TokenResponse:
        if not settings.GOOGLE_CLIENT_ID:
            raise AuthError("GOOGLE_AUTH_DISABLED", "Google Sign-In is not configured on this server", 501)

        try:
            from google.oauth2 import id_token as gid_token
            from google.auth.transport import requests as google_requests

            idinfo = await run_in_threadpool(
                gid_token.verify_oauth2_token,
                google_credential,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID,
            )
        except Exception:
            raise AuthError("INVALID_TOKEN", "Invalid Google credential")

        email = idinfo.get("email")
        if not email or not idinfo.get("email_verified"):
            raise AuthError("INVALID_TOKEN", "Google account email is not verified")

        user = await PublicRepository.get_platform_user_by_email(email, db)
        if not user or not user.is_active:
            await AuditService.log(
                AuditEventType.PLATFORM_LOGIN_FAILURE,
                metadata={"attempted_email": email, "method": "google"},
                ip_address=ip, user_agent=user_agent,
            )
            raise AuthError("UNAUTHORIZED", "This Google account is not authorized as a Super Admin", 403)

        expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            {
                "sub": str(user.id),
                "tenant_id": None,
                "schema_name": None,
                "role": "SUPER_ADMIN",
                "email": user.email,
            },
            expires_delta=expires,
        )
        raw_refresh = generate_refresh_token()
        token_hash = hash_token(raw_refresh)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        await PublicRepository.create_platform_refresh_token(
            user.id, token_hash, expires_at, ip, user_agent, db
        )
        await PublicRepository.update_platform_user(
            user.id, {"last_login_at": datetime.now(timezone.utc)}, db
        )
        await db.commit()
        await AuditService.log(
            AuditEventType.PLATFORM_LOGIN_SUCCESS,
            actor_user_id=user.id, actor_role="SUPER_ADMIN",
            ip_address=ip, user_agent=user_agent,
            metadata={"method": "google"},
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            expires_in=int(expires.total_seconds()),
        )

    @staticmethod
    async def refresh_tokens(
        raw_token: str,
        ip: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> TokenResponse:
        token_hash = hash_token(raw_token)
        record = await PublicRepository.get_platform_refresh_token_by_hash(token_hash, db)
        if not record:
            raise AuthError("INVALID_TOKEN", "Invalid refresh token")
        if record.is_revoked:
            await PublicRepository.revoke_all_platform_user_refresh_tokens(record.user_id, db)
            await AuditService.log(
                AuditEventType.PLATFORM_TOKEN_REUSE_DETECTED,
                actor_user_id=record.user_id, actor_role="SUPER_ADMIN",
                ip_address=ip, user_agent=user_agent,
            )
            raise AuthError("INVALID_TOKEN", "Refresh token reuse detected")
        if _as_utc(record.expires_at) < datetime.now(timezone.utc):
            raise AuthError("INVALID_TOKEN", "Refresh token expired")

        user = await PublicRepository.get_platform_user_by_id(record.user_id, db)
        if not user or not user.is_active:
            raise AuthError("INVALID_TOKEN", "User inactive")

        new_raw = generate_refresh_token()
        new_hash = hash_token(new_raw)
        new_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        new_record = await PublicRepository.create_platform_refresh_token(
            user.id, new_hash, new_expires_at, ip, user_agent, db
        )
        await PublicRepository.revoke_platform_refresh_token(record.id, new_record.id, db)

        expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            {
                "sub": str(user.id),
                "tenant_id": None,
                "schema_name": None,
                "role": "SUPER_ADMIN",
                "email": user.email,
            },
            expires_delta=expires,
        )
        await AuditService.log(
            AuditEventType.PLATFORM_TOKEN_REFRESH,
            actor_user_id=user.id, actor_role="SUPER_ADMIN",
            ip_address=ip, user_agent=user_agent,
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_raw,
            expires_in=int(expires.total_seconds()),
        )

    @staticmethod
    async def logout(
        raw_token: str,
        actor_user_id: UUID | None,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> None:
        token_hash = hash_token(raw_token)
        record = await PublicRepository.get_platform_refresh_token_by_hash(token_hash, db)
        if record and not record.is_revoked:
            await PublicRepository.revoke_platform_refresh_token(record.id, None, db)
        await AuditService.log(
            AuditEventType.PLATFORM_LOGOUT,
            actor_user_id=actor_user_id, actor_role="SUPER_ADMIN",
            ip_address=ip_address, user_agent=user_agent,
        )

    @staticmethod
    async def logout_all(
        user_id: UUID,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> None:
        await PublicRepository.revoke_all_platform_user_refresh_tokens(user_id, db)
        await AuditService.log(
            AuditEventType.PLATFORM_LOGOUT_ALL,
            actor_user_id=user_id, actor_role="SUPER_ADMIN",
            ip_address=ip_address, user_agent=user_agent,
        )

    @staticmethod
    async def request_password_reset(
        email: str,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> None:
        user = await PublicRepository.get_platform_user_by_email(email, db)
        if not user or not user.is_active:
            return  # silent — no enumeration
        await PublicRepository.invalidate_prior_platform_otps(user.id, OTPPurpose.PASSWORD_RESET, db)
        plain_otp = generate_otp()
        otp_hash_val = hash_otp(plain_otp)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
        await PublicRepository.create_platform_otp(
            user.id, otp_hash_val, OTPPurpose.PASSWORD_RESET, expires_at, db
        )
        print(f"[DEV] Platform OTP for {email}: {plain_otp}")  # Phase 0: email not wired
        await AuditService.log(
            AuditEventType.PLATFORM_PASSWORD_RESET_REQUESTED,
            actor_user_id=user.id, actor_role="SUPER_ADMIN",
            ip_address=ip_address, user_agent=user_agent,
        )

    @staticmethod
    async def verify_otp_and_issue_reset_token(
        email: str,
        otp_plain: str,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> PasswordResetTokenResponse:
        user = await PublicRepository.get_platform_user_by_email(email, db)
        if not user or not user.is_active:
            raise AuthError("INVALID_CREDENTIALS", "Invalid credentials")
        otp_record = await PublicRepository.get_active_platform_otp(
            user.id, OTPPurpose.PASSWORD_RESET, db
        )
        if not otp_record:
            raise AuthError("OTP_INVALID", "No active OTP")
        await PublicRepository.increment_platform_otp_attempts(otp_record.id, db)
        if otp_record.attempts + 1 > settings.OTP_MAX_ATTEMPTS:
            await PublicRepository.consume_platform_otp(otp_record.id, db)
            await AuditService.log(
                AuditEventType.PLATFORM_PASSWORD_RESET_OTP_FAILED,
                actor_user_id=user.id, actor_role="SUPER_ADMIN",
                metadata={"attempts": otp_record.attempts + 1},
                ip_address=ip_address, user_agent=user_agent,
            )
            raise AuthError("OTP_MAX_ATTEMPTS", "OTP max attempts exceeded")
        if not verify_otp(otp_plain, otp_record.otp_hash):
            raise AuthError("OTP_INVALID", "Invalid OTP")
        await PublicRepository.consume_platform_otp(otp_record.id, db)
        iat_cutoff = (
            _as_utc(user.password_changed_at)
            if user.password_changed_at
            else datetime(1970, 1, 1, tzinfo=timezone.utc)
        )
        reset_token = create_reset_token(
            user_id=user.id,
            schema_name=None,
            iat_cutoff=iat_cutoff,
            expires_delta=timedelta(minutes=15),
        )
        await AuditService.log(
            AuditEventType.PLATFORM_PASSWORD_RESET_VERIFIED,
            actor_user_id=user.id, actor_role="SUPER_ADMIN",
            ip_address=ip_address, user_agent=user_agent,
        )
        return PasswordResetTokenResponse(reset_token=reset_token)

    @staticmethod
    async def confirm_password_reset(
        reset_token_str: str,
        new_password: str,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> None:
        try:
            payload = decode_token(reset_token_str)
        except JWTError:
            raise AuthError("INVALID_TOKEN", "Invalid or expired reset token")
        if payload.get("purpose") != "PASSWORD_RESET":
            raise AuthError("INVALID_TOKEN", "Invalid token purpose")
        user_id = UUID(payload["sub"])
        iat_cutoff_str = payload.get("iat_cutoff")
        iat_cutoff = (
            datetime.fromisoformat(iat_cutoff_str)
            if iat_cutoff_str
            else datetime(1970, 1, 1, tzinfo=timezone.utc)
        )
        user = await PublicRepository.get_platform_user_by_id(user_id, db)
        if not user or not user.is_active:
            raise AuthError("INVALID_TOKEN", "Invalid reset token")
        if user.password_changed_at and _as_utc(user.password_changed_at) > _as_utc(iat_cutoff):
            raise AuthError("INVALID_TOKEN", "Reset token already used")
        new_hash = hash_password(new_password)
        now = datetime.now(timezone.utc)
        await PublicRepository.update_platform_user(
            user_id, {"password_hash": new_hash, "password_changed_at": now}, db
        )
        await PublicRepository.revoke_all_platform_user_refresh_tokens(user_id, db)
        await AuditService.log(
            AuditEventType.PLATFORM_PASSWORD_RESET_COMPLETED,
            actor_user_id=user_id, actor_role="SUPER_ADMIN",
            target_entity="PlatformUser", target_id=str(user_id),
            ip_address=ip_address, user_agent=user_agent,
        )


# ---------------------------------------------------------------------------
# Tenant user auth flows (schema-scoped)
# ---------------------------------------------------------------------------

class TenantAuthService:

    @staticmethod
    async def login(
        email: str,
        password: str,
        tenant_id: UUID,
        schema_name: str,
        ip: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> TokenResponse:
        user = await TenantRepository.get_user_by_email(email, db)
        if not user or not user.is_active:
            await AuditService.log(
                AuditEventType.AUTH_LOGIN_FAILURE,
                actor_role=None, tenant_id=tenant_id, schema_name=schema_name,
                metadata={"attempted_email": email, "reason": "user_not_found_or_inactive"},
                ip_address=ip, user_agent=user_agent,
            )
            raise AuthError("INVALID_CREDENTIALS", "Invalid credentials")
        if not verify_password(password, user.password_hash):
            await AuditService.log(
                AuditEventType.AUTH_LOGIN_FAILURE,
                actor_user_id=user.id, actor_role=user.role.value,
                tenant_id=tenant_id, schema_name=schema_name,
                target_entity="User", target_id=str(user.id),
                metadata={"reason": "invalid_password"},
                ip_address=ip, user_agent=user_agent,
            )
            raise AuthError("INVALID_CREDENTIALS", "Invalid credentials")

        expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            {
                "sub": str(user.id),
                "tenant_id": str(tenant_id),
                "schema_name": schema_name,
                "role": user.role.value,
                "email": user.email,
            },
            expires_delta=expires,
        )
        raw_refresh = generate_refresh_token()
        token_hash = hash_token(raw_refresh)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        await TenantRepository.create_refresh_token(
            user.id, token_hash, expires_at, schema_name, ip, user_agent, db
        )
        await TenantRepository.update_user(
            user.id, {"last_login_at": datetime.now(timezone.utc)}, db
        )
        await db.commit()
        await AuditService.log(
            AuditEventType.AUTH_LOGIN_SUCCESS,
            actor_user_id=user.id, actor_role=user.role.value,
            tenant_id=tenant_id, schema_name=schema_name,
            target_entity="User", target_id=str(user.id),
            ip_address=ip, user_agent=user_agent,
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            expires_in=int(expires.total_seconds()),
        )

    @staticmethod
    async def refresh_tokens(
        raw_token: str,
        ip: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> TokenResponse:
        token_hash = hash_token(raw_token)
        index_entry = await PublicRepository.get_index_entry_by_hash(token_hash, db)
        if not index_entry:
            raise AuthError("INVALID_TOKEN", "Invalid refresh token")
        if index_entry.schema_name is None:
            return await PlatformAuthService.refresh_tokens(raw_token, ip, user_agent, db)

        schema_name = index_entry.schema_name
        tenant = await PublicRepository.get_tenant_by_schema_name(schema_name, db)
        if not tenant:
            raise AuthError("INVALID_TOKEN", "Tenant not found")

        async with _open_tenant_session(schema_name) as tenant_db:
            record = await TenantRepository.get_refresh_token_by_hash(token_hash, tenant_db)
            if not record:
                raise AuthError("INVALID_TOKEN", "Invalid refresh token")
            if record.is_revoked:
                await TenantRepository.revoke_all_user_refresh_tokens(record.user_id, schema_name, tenant_db)
                await tenant_db.commit()
                await AuditService.log(
                    AuditEventType.AUTH_TOKEN_REUSE_DETECTED,
                    actor_user_id=record.user_id, schema_name=schema_name,
                    tenant_id=tenant.id, ip_address=ip, user_agent=user_agent,
                )
                raise AuthError("INVALID_TOKEN", "Refresh token reuse detected")
            if _as_utc(record.expires_at) < datetime.now(timezone.utc):
                raise AuthError("INVALID_TOKEN", "Refresh token expired")

            user = await TenantRepository.get_user_by_id(record.user_id, tenant_db)
            if not user or not user.is_active:
                raise AuthError("INVALID_TOKEN", "User inactive")

            new_raw = generate_refresh_token()
            new_hash = hash_token(new_raw)
            new_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
            new_record = await TenantRepository.create_refresh_token(
                user.id, new_hash, new_expires_at, schema_name, ip, user_agent, tenant_db
            )
            await TenantRepository.revoke_refresh_token(record.id, new_record.id, tenant_db)

            expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = create_access_token(
                {
                    "sub": str(user.id),
                    "tenant_id": str(tenant.id),
                    "schema_name": schema_name,
                    "role": user.role.value,
                    "email": user.email,
                },
                expires_delta=expires,
            )
            await AuditService.log(
                AuditEventType.AUTH_TOKEN_REFRESH,
                actor_user_id=user.id, actor_role=user.role.value,
                tenant_id=tenant.id, schema_name=schema_name,
                ip_address=ip, user_agent=user_agent,
            )
            return TokenResponse(
                access_token=access_token,
                refresh_token=new_raw,
                expires_in=int(expires.total_seconds()),
            )

    @staticmethod
    async def logout(
        raw_token: str,
        actor_user_id: UUID | None,
        actor_role: str | None,
        tenant_id: UUID | None,
        schema_name: str | None,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> None:
        token_hash = hash_token(raw_token)
        index_entry = await PublicRepository.get_index_entry_by_hash(token_hash, db)
        if not index_entry:
            return  # idempotent
        if index_entry.schema_name is None:
            await PlatformAuthService.logout(raw_token, actor_user_id, ip_address, user_agent, db)
            return
        async with _open_tenant_session(index_entry.schema_name) as tenant_db:
            record = await TenantRepository.get_refresh_token_by_hash(token_hash, tenant_db)
            if record and not record.is_revoked:
                await TenantRepository.revoke_refresh_token(record.id, None, tenant_db)
        await AuditService.log(
            AuditEventType.AUTH_LOGOUT,
            actor_user_id=actor_user_id, actor_role=actor_role,
            tenant_id=tenant_id, schema_name=schema_name,
            ip_address=ip_address, user_agent=user_agent,
        )

    @staticmethod
    async def logout_all(
        user_id: UUID,
        actor_role: str | None,
        tenant_id: UUID | None,
        schema_name: str,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> None:
        async with _open_tenant_session(schema_name) as tenant_db:
            await TenantRepository.revoke_all_user_refresh_tokens(user_id, schema_name, tenant_db)
        await AuditService.log(
            AuditEventType.AUTH_LOGOUT_ALL,
            actor_user_id=user_id, actor_role=actor_role,
            tenant_id=tenant_id, schema_name=schema_name,
            ip_address=ip_address, user_agent=user_agent,
        )

    @staticmethod
    async def request_password_reset(
        email: str,
        tenant_id: UUID,
        schema_name: str,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> None:
        user = await TenantRepository.get_user_by_email(email, db)
        if not user or not user.is_active:
            return  # silent — no enumeration
        await TenantRepository.invalidate_prior_otps(user.id, OTPPurpose.PASSWORD_RESET, db)
        plain_otp = generate_otp()
        otp_hash_val = hash_otp(plain_otp)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
        await TenantRepository.create_otp(
            user.id, otp_hash_val, OTPPurpose.PASSWORD_RESET, expires_at, db
        )
        await db.commit()
        print(f"[DEV] Tenant OTP for {email}: {plain_otp}")  # Phase 0: email not wired
        await AuditService.log(
            AuditEventType.AUTH_PASSWORD_RESET_REQUESTED,
            actor_user_id=user.id, actor_role=user.role.value,
            tenant_id=tenant_id, schema_name=schema_name,
            target_entity="User", target_id=str(user.id),
            ip_address=ip_address, user_agent=user_agent,
        )

    @staticmethod
    async def verify_otp_and_issue_reset_token(
        email: str,
        otp_plain: str,
        schema_name: str,
        tenant_id: UUID,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> PasswordResetTokenResponse:
        user = await TenantRepository.get_user_by_email(email, db)
        if not user or not user.is_active:
            raise AuthError("INVALID_CREDENTIALS", "Invalid credentials")
        otp_record = await TenantRepository.get_active_otp(
            user.id, OTPPurpose.PASSWORD_RESET, db
        )
        if not otp_record:
            raise AuthError("OTP_INVALID", "No active OTP")
        await TenantRepository.increment_otp_attempts(otp_record.id, db)
        if otp_record.attempts + 1 > settings.OTP_MAX_ATTEMPTS:
            await TenantRepository.consume_otp(otp_record.id, db)
            await db.commit()
            await AuditService.log(
                AuditEventType.AUTH_PASSWORD_RESET_OTP_FAILED,
                actor_user_id=user.id, actor_role=user.role.value,
                tenant_id=tenant_id, schema_name=schema_name,
                metadata={"attempts": otp_record.attempts + 1},
                ip_address=ip_address, user_agent=user_agent,
            )
            raise AuthError("OTP_MAX_ATTEMPTS", "OTP max attempts exceeded")
        if not verify_otp(otp_plain, otp_record.otp_hash):
            await db.commit()
            raise AuthError("OTP_INVALID", "Invalid OTP")
        await TenantRepository.consume_otp(otp_record.id, db)
        await db.commit()
        iat_cutoff = (
            _as_utc(user.password_changed_at)
            if user.password_changed_at
            else datetime(1970, 1, 1, tzinfo=timezone.utc)
        )
        reset_token = create_reset_token(
            user_id=user.id,
            schema_name=schema_name,
            iat_cutoff=iat_cutoff,
            expires_delta=timedelta(minutes=15),
        )
        await AuditService.log(
            AuditEventType.AUTH_PASSWORD_RESET_VERIFIED,
            actor_user_id=user.id, actor_role=user.role.value,
            tenant_id=tenant_id, schema_name=schema_name,
            ip_address=ip_address, user_agent=user_agent,
        )
        return PasswordResetTokenResponse(reset_token=reset_token)

    @staticmethod
    async def confirm_password_reset(
        reset_token_str: str,
        new_password: str,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> None:
        try:
            payload = decode_token(reset_token_str)
        except JWTError:
            raise AuthError("INVALID_TOKEN", "Invalid or expired reset token")
        if payload.get("purpose") != "PASSWORD_RESET":
            raise AuthError("INVALID_TOKEN", "Invalid token purpose")
        schema_name = payload.get("schema_name")
        if not schema_name:
            raise AuthError("INVALID_TOKEN", "Invalid reset token")
        user_id = UUID(payload["sub"])
        iat_cutoff_str = payload.get("iat_cutoff")
        iat_cutoff = (
            datetime.fromisoformat(iat_cutoff_str)
            if iat_cutoff_str
            else datetime(1970, 1, 1, tzinfo=timezone.utc)
        )
        async with _open_tenant_session(schema_name) as tenant_db:
            user = await TenantRepository.get_user_by_id(user_id, tenant_db)
            if not user or not user.is_active:
                raise AuthError("INVALID_TOKEN", "Invalid reset token")
            if user.password_changed_at and _as_utc(user.password_changed_at) > _as_utc(iat_cutoff):
                raise AuthError("INVALID_TOKEN", "Reset token already used")
            new_hash = hash_password(new_password)
            now = datetime.now(timezone.utc)
            await TenantRepository.update_user(
                user_id, {"password_hash": new_hash, "password_changed_at": now}, tenant_db
            )
            await TenantRepository.revoke_all_user_refresh_tokens(user_id, schema_name, tenant_db)
            tenant = await PublicRepository.get_tenant_by_schema_name(schema_name, tenant_db)
            await AuditService.log(
                AuditEventType.AUTH_PASSWORD_RESET_COMPLETED,
                actor_user_id=user_id, schema_name=schema_name,
                tenant_id=tenant.id if tenant else None,
                target_entity="User", target_id=str(user_id),
                ip_address=ip_address, user_agent=user_agent,
            )

    @staticmethod
    async def create_user(
        payload: CreateUserRequest,
        actor_user_id: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> UserResponse:
        existing = await TenantRepository.get_user_by_email(payload.email, db)
        if existing:
            raise AuthError("EMAIL_EXISTS", "Email already registered", 409)
        pw_hash = hash_password(payload.password)
        user = await TenantRepository.create_user(
            payload.email, pw_hash, payload.role, payload.full_name, payload.identifier, db
        )
        await AuditService.log(
            AuditEventType.USER_CREATED,
            actor_user_id=actor_user_id, actor_role=actor_role,
            tenant_id=tenant_id, schema_name=schema_name,
            target_entity="User", target_id=str(user.id),
            metadata={"email": payload.email, "role": payload.role.value},
            ip_address=ip_address, user_agent=user_agent,
        )
        return UserResponse.model_validate(user)

    @staticmethod
    async def update_user(
        user_id: UUID,
        payload: UpdateUserRequest,
        actor_user_id: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> UserResponse:
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            raise AuthError("NO_FIELDS", "No fields to update", 422)
        user = await TenantRepository.update_user(user_id, updates, db)
        if not user:
            raise AuthError("USER_NOT_FOUND", "User not found", 404)

        if "is_active" in updates and updates["is_active"] is False:
            event = AuditEventType.USER_DEACTIVATED
        elif "role" in updates:
            event = AuditEventType.USER_ROLE_CHANGED
        else:
            event = AuditEventType.USER_UPDATED

        await AuditService.log(
            event,
            actor_user_id=actor_user_id, actor_role=actor_role,
            tenant_id=tenant_id, schema_name=schema_name,
            target_entity="User", target_id=str(user_id),
            metadata={"changes": updates},
            ip_address=ip_address, user_agent=user_agent,
        )
        return UserResponse.model_validate(user)

    @staticmethod
    async def change_password(
        user_id: UUID,
        current_password: str,
        new_password: str,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> None:
        user = await TenantRepository.get_user_by_id(user_id, db)
        if not user:
            raise AuthError("USER_NOT_FOUND", "User not found", 404)
        if not verify_password(current_password, user.password_hash):
            raise AuthError("INVALID_CREDENTIALS", "Current password is incorrect", 401)
        new_hash = hash_password(new_password)
        now = datetime.now(timezone.utc)
        await TenantRepository.update_user(
            user_id,
            {
                "password_hash": new_hash,
                "password_changed_at": now,
                "must_change_password": False,
            },
            db,
        )
        await TenantRepository.revoke_all_user_refresh_tokens(user_id, schema_name, db)
        await AuditService.log(
            AuditEventType.AUTH_PASSWORD_CHANGED,
            actor_user_id=user_id, actor_role=actor_role,
            tenant_id=tenant_id, schema_name=schema_name,
            target_entity="User", target_id=str(user_id),
            ip_address=ip_address, user_agent=user_agent,
        )
