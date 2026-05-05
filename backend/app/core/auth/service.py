import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.core.auth.models import OTPPurpose
from app.core.auth.repository import PublicRepository, TenantRepository
from app.core.auth.schemas import (
    CreateUserRequest,
    PasswordResetTokenResponse,
    TokenResponse,
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
            raise AuthError("INVALID_CREDENTIALS", "Invalid credentials")
        if not verify_password(password, user.password_hash):
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
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_raw,
            expires_in=int(expires.total_seconds()),
        )

    @staticmethod
    async def logout(raw_token: str, db: AsyncSession) -> None:
        token_hash = hash_token(raw_token)
        record = await PublicRepository.get_platform_refresh_token_by_hash(token_hash, db)
        if record and not record.is_revoked:
            await PublicRepository.revoke_platform_refresh_token(record.id, None, db)

    @staticmethod
    async def logout_all(user_id: UUID, db: AsyncSession) -> None:
        await PublicRepository.revoke_all_platform_user_refresh_tokens(user_id, db)

    @staticmethod
    async def request_password_reset(email: str, db: AsyncSession) -> None:
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

    @staticmethod
    async def verify_otp_and_issue_reset_token(
        email: str,
        otp_plain: str,
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
        return PasswordResetTokenResponse(reset_token=reset_token)

    @staticmethod
    async def confirm_password_reset(
        reset_token_str: str,
        new_password: str,
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
            raise AuthError("INVALID_CREDENTIALS", "Invalid credentials")
        if not verify_password(password, user.password_hash):
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
            return TokenResponse(
                access_token=access_token,
                refresh_token=new_raw,
                expires_in=int(expires.total_seconds()),
            )

    @staticmethod
    async def logout(raw_token: str, db: AsyncSession) -> None:
        token_hash = hash_token(raw_token)
        index_entry = await PublicRepository.get_index_entry_by_hash(token_hash, db)
        if not index_entry:
            return  # idempotent
        if index_entry.schema_name is None:
            await PlatformAuthService.logout(raw_token, db)
            return
        schema_name = index_entry.schema_name
        async with _open_tenant_session(schema_name) as tenant_db:
            record = await TenantRepository.get_refresh_token_by_hash(token_hash, tenant_db)
            if record and not record.is_revoked:
                await TenantRepository.revoke_refresh_token(record.id, None, tenant_db)

    @staticmethod
    async def logout_all(user_id: UUID, schema_name: str, db: AsyncSession) -> None:
        async with _open_tenant_session(schema_name) as tenant_db:
            await TenantRepository.revoke_all_user_refresh_tokens(user_id, schema_name, tenant_db)

    @staticmethod
    async def request_password_reset(email: str, db: AsyncSession) -> None:
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
        print(f"[DEV] Tenant OTP for {email}: {plain_otp}")  # Phase 0: email not wired

    @staticmethod
    async def verify_otp_and_issue_reset_token(
        email: str,
        otp_plain: str,
        schema_name: str,
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
            raise AuthError("OTP_MAX_ATTEMPTS", "OTP max attempts exceeded")
        if not verify_otp(otp_plain, otp_record.otp_hash):
            raise AuthError("OTP_INVALID", "Invalid OTP")
        await TenantRepository.consume_otp(otp_record.id, db)
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
        return PasswordResetTokenResponse(reset_token=reset_token)

    @staticmethod
    async def confirm_password_reset(
        reset_token_str: str,
        new_password: str,
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

    @staticmethod
    async def create_user(payload: CreateUserRequest, db: AsyncSession) -> UserResponse:
        existing = await TenantRepository.get_user_by_email(payload.email, db)
        if existing:
            raise AuthError("EMAIL_EXISTS", "Email already registered", 409)
        pw_hash = hash_password(payload.password)
        user = await TenantRepository.create_user(
            payload.email, pw_hash, payload.role, payload.full_name, payload.identifier, db
        )
        return UserResponse.model_validate(user)
