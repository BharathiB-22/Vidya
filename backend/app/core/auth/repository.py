from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update, delete, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.models import (
    User, RefreshToken, OTPCode,
    PlatformUser, PlatformRefreshToken, PlatformOTPCode,
    RefreshTokenIndex, OTPPurpose, Tenant,
)


class PublicRepository:

    @staticmethod
    async def get_tenant_by_slug(slug: str, db: AsyncSession):
        stmt = select(Tenant).where(Tenant.slug == slug)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_platform_user_by_email(email: str, db: AsyncSession):
        stmt = select(PlatformUser).where(PlatformUser.email == email)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_platform_user_by_id(user_id: UUID, db: AsyncSession):
        stmt = select(PlatformUser).where(PlatformUser.id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_platform_user(user_id: UUID, updates: dict, db: AsyncSession):
        stmt = select(PlatformUser).where(PlatformUser.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            return None
        for key, value in updates.items():
            setattr(user, key, value)
        await db.flush()
        await db.refresh(user)
        return user

    @staticmethod
    async def create_platform_refresh_token(
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ):
        token = PlatformRefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(token)
        await db.flush()
        await db.refresh(token)

        index_entry = RefreshTokenIndex(
            token_hash=token_hash,
            schema_name=None,
            user_id=user_id,
        )
        db.add(index_entry)
        await db.flush()

        return token

    @staticmethod
    async def get_platform_refresh_token_by_hash(token_hash: str, db: AsyncSession):
        stmt = select(PlatformRefreshToken).where(PlatformRefreshToken.token_hash == token_hash)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def revoke_platform_refresh_token(
        token_id: UUID,
        replaced_by_id: UUID | None,
        db: AsyncSession,
    ):
        stmt = select(PlatformRefreshToken).where(PlatformRefreshToken.id == token_id)
        result = await db.execute(stmt)
        token = result.scalar_one_or_none()
        if token is None:
            return
        old_hash = token.token_hash
        token.is_revoked = True
        token.replaced_by = replaced_by_id
        await db.flush()

        del_stmt = delete(RefreshTokenIndex).where(RefreshTokenIndex.token_hash == old_hash)
        await db.execute(del_stmt)

    @staticmethod
    async def revoke_all_platform_user_refresh_tokens(user_id: UUID, db: AsyncSession):
        upd_stmt = (
            update(PlatformRefreshToken)
            .where(PlatformRefreshToken.user_id == user_id)
            .values(is_revoked=True)
        )
        await db.execute(upd_stmt)

        del_stmt = delete(RefreshTokenIndex).where(
            and_(
                RefreshTokenIndex.user_id == user_id,
                RefreshTokenIndex.schema_name.is_(None),
            )
        )
        await db.execute(del_stmt)

    @staticmethod
    async def create_platform_otp(
        user_id: UUID,
        otp_hash: str,
        purpose: OTPPurpose,
        expires_at: datetime,
        db: AsyncSession,
    ):
        otp = PlatformOTPCode(
            user_id=user_id,
            otp_hash=otp_hash,
            purpose=purpose,
            expires_at=expires_at,
        )
        db.add(otp)
        await db.flush()
        await db.refresh(otp)
        return otp

    @staticmethod
    async def get_active_platform_otp(
        user_id: UUID,
        purpose: OTPPurpose,
        db: AsyncSession,
    ):
        now = datetime.now(timezone.utc)
        stmt = select(PlatformOTPCode).where(
            and_(
                PlatformOTPCode.user_id == user_id,
                PlatformOTPCode.purpose == purpose,
                PlatformOTPCode.is_used.is_(False),
                PlatformOTPCode.expires_at > now,
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def increment_platform_otp_attempts(otp_id: UUID, db: AsyncSession):
        stmt = select(PlatformOTPCode).where(PlatformOTPCode.id == otp_id)
        result = await db.execute(stmt)
        otp = result.scalar_one_or_none()
        if otp is None:
            return
        otp.attempts = otp.attempts + 1
        await db.flush()

    @staticmethod
    async def consume_platform_otp(otp_id: UUID, db: AsyncSession):
        stmt = select(PlatformOTPCode).where(PlatformOTPCode.id == otp_id)
        result = await db.execute(stmt)
        otp = result.scalar_one_or_none()
        if otp is None:
            return
        otp.is_used = True
        await db.flush()

    @staticmethod
    async def invalidate_prior_platform_otps(
        user_id: UUID,
        purpose: OTPPurpose,
        db: AsyncSession,
    ):
        stmt = (
            update(PlatformOTPCode)
            .where(
                and_(
                    PlatformOTPCode.user_id == user_id,
                    PlatformOTPCode.purpose == purpose,
                    PlatformOTPCode.is_used.is_(False),
                )
            )
            .values(is_used=True)
        )
        await db.execute(stmt)

    @staticmethod
    async def get_tenant_by_schema_name(schema_name: str, db: AsyncSession):
        stmt = select(Tenant).where(Tenant.schema_name == schema_name)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_tenant_branding(
        tenant_id: UUID,
        logo_url: str | None,
        primary_color: str | None,
        secondary_color: str | None,
        db: AsyncSession,
    ):
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        result = await db.execute(stmt)
        tenant = result.scalar_one_or_none()
        if tenant is None:
            return None
        tenant.logo_url = logo_url
        tenant.primary_color = primary_color
        tenant.secondary_color = secondary_color
        await db.flush()
        await db.refresh(tenant)
        return tenant

    @staticmethod
    async def get_index_entry_by_hash(token_hash: str, db: AsyncSession):
        stmt = select(RefreshTokenIndex).where(RefreshTokenIndex.token_hash == token_hash)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_index_entry(token_hash: str, db: AsyncSession):
        stmt = delete(RefreshTokenIndex).where(RefreshTokenIndex.token_hash == token_hash)
        await db.execute(stmt)

    @staticmethod
    async def delete_index_entries_for_user(
        user_id: UUID,
        schema_name: str | None,
        db: AsyncSession,
    ):
        if schema_name is None:
            condition = and_(
                RefreshTokenIndex.user_id == user_id,
                RefreshTokenIndex.schema_name.is_(None),
            )
        else:
            condition = and_(
                RefreshTokenIndex.user_id == user_id,
                RefreshTokenIndex.schema_name == schema_name,
            )
        stmt = delete(RefreshTokenIndex).where(condition)
        await db.execute(stmt)


class TenantRepository:

    @staticmethod
    async def get_user_by_email(email: str, db: AsyncSession):
        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_id(user_id: UUID, db: AsyncSession):
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_user(
        email: str,
        password_hash: str,
        role: str,
        full_name: str,
        identifier: str | None,
        db: AsyncSession,
    ):
        user = User(
            email=email,
            password_hash=password_hash,
            role=role,
            full_name=full_name,
            identifier=identifier,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        return user

    @staticmethod
    async def update_user(user_id: UUID, updates: dict, db: AsyncSession):
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            return None
        for key, value in updates.items():
            setattr(user, key, value)
        await db.flush()
        await db.refresh(user)
        return user

    @staticmethod
    async def list_users(db: AsyncSession):
        stmt = select(User).order_by(User.created_at.desc())
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def list_active_guides(db: AsyncSession):
        from app.core.auth.models import TenantRole
        stmt = (
            select(User)
            .where(User.role == TenantRole.GUIDE, User.is_active.is_(True))
            .order_by(User.full_name)
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def create_refresh_token(
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        schema_name: str,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ):
        token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(token)
        await db.flush()
        await db.refresh(token)

        index_entry = RefreshTokenIndex(
            token_hash=token_hash,
            schema_name=schema_name,
            user_id=user_id,
        )
        db.add(index_entry)
        await db.flush()

        return token

    @staticmethod
    async def get_refresh_token_by_hash(token_hash: str, db: AsyncSession):
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def revoke_refresh_token(
        token_id: UUID,
        replaced_by_id: UUID | None,
        db: AsyncSession,
    ):
        stmt = select(RefreshToken).where(RefreshToken.id == token_id)
        result = await db.execute(stmt)
        token = result.scalar_one_or_none()
        if token is None:
            return
        old_hash = token.token_hash
        token.is_revoked = True
        token.replaced_by = replaced_by_id
        await db.flush()

        # Only purge the index entry on explicit revocation (logout/cascade).
        # During rotation (replaced_by_id is set) keep it so reuse detection can fire.
        if replaced_by_id is None:
            del_stmt = delete(RefreshTokenIndex).where(RefreshTokenIndex.token_hash == old_hash)
            await db.execute(del_stmt)

    @staticmethod
    async def revoke_all_user_refresh_tokens(
        user_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ):
        upd_stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .values(is_revoked=True)
        )
        await db.execute(upd_stmt)

        del_stmt = delete(RefreshTokenIndex).where(
            and_(
                RefreshTokenIndex.user_id == user_id,
                RefreshTokenIndex.schema_name == schema_name,
            )
        )
        await db.execute(del_stmt)

    @staticmethod
    async def create_otp(
        user_id: UUID,
        otp_hash: str,
        purpose: OTPPurpose,
        expires_at: datetime,
        db: AsyncSession,
    ):
        otp = OTPCode(
            user_id=user_id,
            otp_hash=otp_hash,
            purpose=purpose,
            expires_at=expires_at,
        )
        db.add(otp)
        await db.flush()
        await db.refresh(otp)
        return otp

    @staticmethod
    async def get_active_otp(user_id: UUID, purpose: OTPPurpose, db: AsyncSession):
        now = datetime.now(timezone.utc)
        stmt = select(OTPCode).where(
            and_(
                OTPCode.user_id == user_id,
                OTPCode.purpose == purpose,
                OTPCode.is_used.is_(False),
                OTPCode.expires_at > now,
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def increment_otp_attempts(otp_id: UUID, db: AsyncSession):
        stmt = select(OTPCode).where(OTPCode.id == otp_id)
        result = await db.execute(stmt)
        otp = result.scalar_one_or_none()
        if otp is None:
            return
        otp.attempts = otp.attempts + 1
        await db.flush()

    @staticmethod
    async def consume_otp(otp_id: UUID, db: AsyncSession):
        stmt = select(OTPCode).where(OTPCode.id == otp_id)
        result = await db.execute(stmt)
        otp = result.scalar_one_or_none()
        if otp is None:
            return
        otp.is_used = True
        await db.flush()

    @staticmethod
    async def invalidate_prior_otps(
        user_id: UUID,
        purpose: OTPPurpose,
        db: AsyncSession,
    ):
        stmt = (
            update(OTPCode)
            .where(
                and_(
                    OTPCode.user_id == user_id,
                    OTPCode.purpose == purpose,
                    OTPCode.is_used.is_(False),
                )
            )
            .values(is_used=True)
        )
        await db.execute(stmt)
