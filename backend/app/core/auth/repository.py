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
    async def list_users(
        db: AsyncSession,
        acad_program_id: UUID | None = None,
    ) -> list[dict]:
        """Return all users with academic ownership fields pre-populated.

        Joins sis_faculty_profiles and sis_student_profiles to surface
        faculty_code, USN, home department, and teaching/governance programs
        in a single efficient pass over the database.
        """
        where_clause = "WHERE u.acad_program_id = :pid" if acad_program_id else ""
        main_sql = text(f"""
            SELECT
                u.id,
                u.email,
                u.role,
                u.full_name,
                u.identifier,
                u.acad_program_id,
                u.is_active,
                u.must_change_password,
                u.created_at,
                p.id   AS enrolled_program_id,
                p.name AS program_name,
                -- Department: faculty/dean from profile, student from their program's dept
                COALESCE(fd.name, sd.name) AS department_name,
                COALESCE(fd.code, sd.code) AS department_code,
                fp.faculty_code,
                sp.usn
            FROM users u
            LEFT JOIN acad_programs        p  ON p.id  = u.acad_program_id
            LEFT JOIN acad_departments     sd ON sd.id = p.department_id
            LEFT JOIN sis_faculty_profiles fp ON fp.user_id = u.id
            LEFT JOIN sis_student_profiles sp ON sp.user_id = u.id
            LEFT JOIN acad_departments     fd ON fd.id = fp.primary_department_id
            {where_clause}
            ORDER BY u.created_at DESC
        """)
        params = {"pid": acad_program_id} if acad_program_id else {}
        rows = (await db.execute(main_sql, params)).mappings().all()

        user_ids = [str(r["id"]) for r in rows]
        grants_map: dict[str, list[str]] = {}
        fpa_names: dict[str, list[str]] = {}   # faculty teaching programs
        fpa_ids:   dict[str, list[str]] = {}
        dpa_names: dict[str, list[str]] = {}   # dean governance programs
        dpa_ids:   dict[str, list[str]] = {}

        if user_ids:
            # Role grants
            grant_rows = await db.execute(
                text(
                    "SELECT faculty_user_id::text, role_code "
                    "FROM faculty_role_grants "
                    "WHERE is_active = true AND faculty_user_id = ANY(:ids)"
                ),
                {"ids": user_ids},
            )
            for uid, code in grant_rows.fetchall():
                grants_map.setdefault(uid, []).append(code)

            # Faculty teaching programs — explicit FPA rows UNION derived from
            # subject_assignments → courses → programs → acad_programs.
            # Deduplication on (faculty_user_id, program_id); NULL acad_program_id excluded.
            fpa_rows = await db.execute(
                text(
                    "WITH combined AS ("
                    "  SELECT fpa.faculty_user_id::text AS uid, fpa.program_id::text AS pid,"
                    "         p.name AS pname"
                    "  FROM faculty_program_assignments fpa"
                    "  JOIN acad_programs p ON p.id = fpa.program_id"
                    "  WHERE fpa.is_active = true AND fpa.faculty_user_id = ANY(:ids)"
                    "  UNION"
                    "  SELECT sa.faculty_user_id::text, pr.acad_program_id::text, ap.name"
                    "  FROM subject_assignments sa"
                    "  JOIN courses c   ON c.id  = sa.course_id"
                    "  JOIN programs pr ON pr.id = c.program_id"
                    "  JOIN acad_programs ap ON ap.id = pr.acad_program_id"
                    "  WHERE sa.is_active = true AND sa.faculty_user_id = ANY(:ids)"
                    "    AND pr.acad_program_id IS NOT NULL"
                    ") "
                    "SELECT uid, pid, pname FROM combined ORDER BY pname"
                ),
                {"ids": user_ids},
            )
            for uid, pid, pname in fpa_rows.fetchall():
                fpa_names.setdefault(uid, []).append(pname)
                fpa_ids.setdefault(uid, []).append(pid)

            # Dean governance programs
            dpa_rows = await db.execute(
                text(
                    "SELECT dpa.dean_user_id::text, dpa.program_id::text, p.name "
                    "FROM dean_program_assignments dpa "
                    "JOIN acad_programs p ON p.id = dpa.program_id "
                    "WHERE dpa.is_active = true AND dpa.dean_user_id = ANY(:ids)"
                ),
                {"ids": user_ids},
            )
            for uid, pid, pname in dpa_rows.fetchall():
                dpa_names.setdefault(uid, []).append(pname)
                dpa_ids.setdefault(uid, []).append(pid)

        result = []
        for r in rows:
            uid  = str(r["id"])
            role = r["role"].value if hasattr(r["role"], "value") else str(r["role"])

            if role in ("FACULTY", "DEAN"):
                academic_id = r["faculty_code"]
            elif role == "STUDENT":
                academic_id = r["usn"]
            else:
                academic_id = None

            if role == "FACULTY":
                program_names = sorted(fpa_names.get(uid, []))
                program_ids   = [i for _, i in sorted(zip(fpa_names.get(uid, []), fpa_ids.get(uid, [])))]
            elif role == "DEAN":
                program_names = sorted(dpa_names.get(uid, []))
                program_ids   = [i for _, i in sorted(zip(dpa_names.get(uid, []), dpa_ids.get(uid, [])))]
            elif role == "STUDENT" and r["enrolled_program_id"]:
                program_names = [r["program_name"]] if r["program_name"] else []
                program_ids   = [str(r["enrolled_program_id"])]
            else:
                program_names = []
                program_ids   = []

            result.append({
                "id":                 r["id"],
                "email":              r["email"],
                "role":               r["role"],
                "full_name":          r["full_name"],
                "identifier":         r["identifier"],
                "acad_program_id":    r["acad_program_id"],
                "acad_program_name":  r["program_name"],
                "department_name":    r["department_name"],
                "department_code":    r["department_code"],
                "academic_id":        academic_id,
                "program_names":      program_names,
                "program_ids":        program_ids,
                "is_active":          r["is_active"],
                "must_change_password": r["must_change_password"],
                "created_at":         r["created_at"],
                "grants":             sorted(grants_map.get(uid, [])),
            })
        return result

    @staticmethod
    async def get_single_user_with_ownership(user_id: UUID, db: AsyncSession) -> dict | None:
        """Return one user enriched with academic ownership fields."""
        main_sql = text("""
            SELECT
                u.id, u.email, u.role, u.full_name, u.identifier,
                u.acad_program_id, u.is_active, u.must_change_password, u.created_at,
                p.id   AS enrolled_program_id,
                p.name AS program_name,
                COALESCE(fd.name, sd.name) AS department_name,
                COALESCE(fd.code, sd.code) AS department_code,
                fp.faculty_code,
                sp.usn
            FROM users u
            LEFT JOIN acad_programs        p  ON p.id  = u.acad_program_id
            LEFT JOIN acad_departments     sd ON sd.id = p.department_id
            LEFT JOIN sis_faculty_profiles fp ON fp.user_id = u.id
            LEFT JOIN sis_student_profiles sp ON sp.user_id = u.id
            LEFT JOIN acad_departments     fd ON fd.id = fp.primary_department_id
            WHERE u.id = :uid
        """)
        result = (await db.execute(main_sql, {"uid": str(user_id)})).mappings().first()
        if result is None:
            return None

        uid_str = str(result["id"])
        grant_rows = await db.execute(
            text("SELECT role_code FROM faculty_role_grants WHERE is_active = true AND faculty_user_id = :u"),
            {"u": uid_str},
        )
        grants = sorted({r[0] for r in grant_rows.fetchall()})

        fpa_rows = await db.execute(
            text("SELECT fpa.program_id::text, p.name FROM faculty_program_assignments fpa JOIN acad_programs p ON p.id = fpa.program_id WHERE fpa.is_active = true AND fpa.faculty_user_id = :u"),
            {"u": uid_str},
        )
        fpa = sorted(fpa_rows.fetchall(), key=lambda x: x[1])

        dpa_rows = await db.execute(
            text("SELECT dpa.program_id::text, p.name FROM dean_program_assignments dpa JOIN acad_programs p ON p.id = dpa.program_id WHERE dpa.is_active = true AND dpa.dean_user_id = :u"),
            {"u": uid_str},
        )
        dpa = sorted(dpa_rows.fetchall(), key=lambda x: x[1])

        role = result["role"].value if hasattr(result["role"], "value") else str(result["role"])
        if role in ("FACULTY", "DEAN"):
            academic_id = result["faculty_code"]
        elif role == "STUDENT":
            academic_id = result["usn"]
        else:
            academic_id = None

        if role == "FACULTY":
            program_names = [n for _, n in fpa]
            program_ids   = [i for i, _ in fpa]
        elif role == "DEAN":
            program_names = [n for _, n in dpa]
            program_ids   = [i for i, _ in dpa]
        elif role == "STUDENT" and result["enrolled_program_id"]:
            program_names = [result["program_name"]] if result["program_name"] else []
            program_ids   = [str(result["enrolled_program_id"])]
        else:
            program_names = []
            program_ids   = []

        return {
            "id":                   result["id"],
            "email":                result["email"],
            "role":                 result["role"],
            "full_name":            result["full_name"],
            "identifier":           result["identifier"],
            "acad_program_id":      result["acad_program_id"],
            "acad_program_name":    result["program_name"],
            "department_name":      result["department_name"],
            "department_code":      result["department_code"],
            "academic_id":          academic_id,
            "program_names":        program_names,
            "program_ids":          program_ids,
            "is_active":            result["is_active"],
            "must_change_password": result["must_change_password"],
            "created_at":           result["created_at"],
            "grants":               grants,
        }

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
