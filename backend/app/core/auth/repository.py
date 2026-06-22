from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update, delete, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.models import (
    User, RefreshToken, OTPCode,
    PlatformUser, PlatformRefreshToken, PlatformOTPCode,
    RefreshTokenIndex, OTPPurpose, Tenant, PlatformBranding,
)
from app.modules.m_academics.models import AcadProgram


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
    async def count_active_platform_sessions(user_id: UUID, db: AsyncSession) -> int:
        now = datetime.now(timezone.utc)
        stmt = select(PlatformRefreshToken).where(
            and_(
                PlatformRefreshToken.user_id == user_id,
                PlatformRefreshToken.is_revoked.is_(False),
                PlatformRefreshToken.expires_at > now,
            )
        )
        result = await db.execute(stmt)
        return len(result.scalars().all())

    @staticmethod
    async def get_platform_branding(db: AsyncSession) -> PlatformBranding | None:
        stmt = select(PlatformBranding).limit(1)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_platform_branding(updates: dict, db: AsyncSession) -> PlatformBranding:
        from datetime import datetime, timezone
        stmt = select(PlatformBranding).limit(1)
        result = await db.execute(stmt)
        branding = result.scalar_one_or_none()
        if branding is None:
            branding = PlatformBranding()
            db.add(branding)
        for key, value in updates.items():
            setattr(branding, key, value)
        branding.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(branding)
        return branding

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
    async def get_program_by_id(program_id: UUID, db: AsyncSession) -> AcadProgram | None:
        result = await db.execute(select(AcadProgram).where(AcadProgram.id == program_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_user(
        email: str,
        password_hash: str,
        role: str,
        full_name: str,
        identifier: str | None,
        db: AsyncSession,
        acad_program_id: UUID | None = None,
    ):
        user = User(
            email=email,
            password_hash=password_hash,
            role=role,
            full_name=full_name,
            identifier=identifier,
            acad_program_id=acad_program_id,
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
    async def list_users(db: AsyncSession, acad_program_id: UUID | None = None):
        stmt = (
            select(User, AcadProgram.name.label("program_name"))
            .outerjoin(AcadProgram, User.acad_program_id == AcadProgram.id)
            .order_by(User.created_at.desc())
        )
        if acad_program_id is not None:
            stmt = stmt.where(User.acad_program_id == acad_program_id)
        result = await db.execute(stmt)
        rows = result.all()
        # Fetch all active grants in one query, keyed by user_id string.
        user_ids = [str(u.id) for u, _ in rows]
        grants_map: dict[str, list[str]] = {}
        if user_ids:
            grants_rows = await db.execute(
                text(
                    "SELECT faculty_user_id::text, role_code "
                    "FROM faculty_role_grants "
                    "WHERE is_active = true AND faculty_user_id = ANY(:ids)"
                ),
                {"ids": user_ids},
            )
            for uid, code in grants_rows.fetchall():
                grants_map.setdefault(uid, []).append(code)
        # Attach program_name and grants as transient attributes.
        users = []
        for user, program_name in rows:
            user._program_name = program_name
            user._grants = sorted(grants_map.get(str(user.id), []))
            users.append(user)
        return users

    @staticmethod
    async def get_academic_overview(db: AsyncSession) -> list[dict]:
        """Return per-program summary: student_count, faculty_count, section_count."""
        rows = await db.execute(
            text(
                """
                SELECT
                    p.id            AS program_id,
                    p.name          AS program_name,
                    p.code          AS program_code,
                    p.degree_type   AS degree_type,
                    p.is_active     AS is_active,
                    COUNT(DISTINCT u.id) FILTER (WHERE u.role = 'STUDENT' AND u.is_active = true) AS student_count,
                    COUNT(DISTINCT sa.faculty_user_id) FILTER (WHERE sa.is_active = true)          AS faculty_count,
                    COUNT(DISTINCT sec.id) FILTER (WHERE sec.is_active = true)                     AS section_count
                FROM acad_programs p
                LEFT JOIN users u
                    ON u.acad_program_id = p.id
                LEFT JOIN acad_batches bat
                    ON bat.program_id = p.id AND bat.is_active = true
                LEFT JOIN acad_semesters sem
                    ON sem.batch_id = bat.id AND sem.is_active = true
                LEFT JOIN acad_sections sec
                    ON sec.semester_id = sem.id AND sec.is_active = true
                LEFT JOIN subject_assignments sa
                    ON sa.semester_id = sem.id AND sa.is_active = true
                WHERE p.is_active = true
                GROUP BY p.id, p.name, p.code, p.degree_type, p.is_active
                ORDER BY p.name
                """
            )
        )
        return [dict(r._mapping) for r in rows.fetchall()]

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
