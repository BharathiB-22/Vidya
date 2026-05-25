import uuid as _uuid
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.onboarding.models import AcademicDepartment, AcademicProgram


class OnboardingRepository:

    # ------------------------------------------------------------------ #
    # Departments                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def list_departments(db: AsyncSession) -> list[AcademicDepartment]:
        result = await db.execute(
            select(AcademicDepartment)
            .where(AcademicDepartment.is_active.is_(True))
            .order_by(AcademicDepartment.name)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_department_by_code(code: str, db: AsyncSession) -> AcademicDepartment | None:
        result = await db.execute(
            select(AcademicDepartment).where(AcademicDepartment.code == code.upper())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_department(
        name: str, code: str, db: AsyncSession
    ) -> AcademicDepartment:
        dept = AcademicDepartment(id=_uuid.uuid4(), name=name, code=code.upper())
        db.add(dept)
        await db.flush()
        await db.refresh(dept)
        return dept

    # ------------------------------------------------------------------ #
    # Programs                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def list_programs(db: AsyncSession) -> list[AcademicProgram]:
        result = await db.execute(
            select(AcademicProgram)
            .where(AcademicProgram.is_active.is_(True))
            .order_by(AcademicProgram.code)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_program_by_id(program_id: UUID, db: AsyncSession) -> AcademicProgram | None:
        result = await db.execute(
            select(AcademicProgram).where(AcademicProgram.id == program_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_program_by_code(code: str, db: AsyncSession) -> AcademicProgram | None:
        result = await db.execute(
            select(AcademicProgram).where(AcademicProgram.code == code.upper())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_program(
        name: str,
        code: str,
        dept_id: UUID | None,
        duration_years: int,
        db: AsyncSession,
    ) -> AcademicProgram:
        prog = AcademicProgram(
            id=_uuid.uuid4(),
            name=name,
            code=code.upper(),
            dept_id=dept_id,
            duration_years=duration_years,
        )
        db.add(prog)
        await db.flush()
        await db.refresh(prog)
        return prog

    # ------------------------------------------------------------------ #
    # Duplicate-check helpers (raw SQL to stay in current search_path)    #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def get_existing_identifiers(identifiers: list[str], db: AsyncSession) -> set[str]:
        if not identifiers:
            return set()
        result = await db.execute(
            text("SELECT identifier FROM users WHERE identifier = ANY(:ids)"),
            {"ids": identifiers},
        )
        return {row[0] for row in result.fetchall()}

    @staticmethod
    async def get_existing_emails(emails: list[str], db: AsyncSession) -> set[str]:
        """Case-insensitive email existence check."""
        if not emails:
            return set()
        lowered = [e.lower() for e in emails]
        result = await db.execute(
            text("SELECT LOWER(email) FROM users WHERE LOWER(email) = ANY(:emails)"),
            {"emails": lowered},
        )
        return {row[0] for row in result.fetchall()}

    # ------------------------------------------------------------------ #
    # Bulk user insert (raw SQL to avoid asyncpg native-enum OID issues)  #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def bulk_insert_users(rows: list[dict], db: AsyncSession) -> int:
        """Insert user rows atomically.

        Each dict must contain: id, email, pw_hash, role, full_name, identifier.
        Uses CAST(:role AS tenantrole) so PostgreSQL resolves the enum from
        the current search_path rather than relying on SQLAlchemy metadata.
        """
        if not rows:
            return 0
        for row in rows:
            await db.execute(
                text(
                    "INSERT INTO users "
                    "    (id, email, password_hash, role, full_name, identifier, "
                    "     is_active, must_change_password) "
                    "VALUES "
                    "    (:id, :email, :pw_hash, CAST(:role AS tenantrole), "
                    "     :full_name, :identifier, true, true)"
                ),
                row,
            )
        return len(rows)
