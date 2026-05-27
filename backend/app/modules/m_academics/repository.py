from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m_academics.models import (
    AcadBatch, AcadDepartment, AcadProgram,
    AcadSection, AcadSemester,
)


class DepartmentRepo:

    @staticmethod
    async def create(
        name: str,
        code: str,
        description: str | None,
        db: AsyncSession,
    ) -> AcadDepartment:
        dept = AcadDepartment(name=name, code=code, description=description)
        db.add(dept)
        await db.flush()
        await db.refresh(dept)
        return dept

    @staticmethod
    async def get_by_id(dept_id: UUID, db: AsyncSession) -> AcadDepartment | None:
        result = await db.execute(select(AcadDepartment).where(AcadDepartment.id == dept_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_name(name: str, db: AsyncSession) -> AcadDepartment | None:
        result = await db.execute(select(AcadDepartment).where(AcadDepartment.name == name))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_code(code: str, db: AsyncSession) -> AcadDepartment | None:
        result = await db.execute(select(AcadDepartment).where(AcadDepartment.code == code))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(db: AsyncSession, include_inactive: bool = False) -> list[AcadDepartment]:
        stmt = select(AcadDepartment).order_by(AcadDepartment.name)
        if not include_inactive:
            stmt = stmt.where(AcadDepartment.is_active.is_(True))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update(dept: AcadDepartment, updates: dict, db: AsyncSession) -> AcadDepartment:
        for key, val in updates.items():
            setattr(dept, key, val)
        dept.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(dept)
        return dept

    @staticmethod
    async def has_active_programs(dept_id: UUID, db: AsyncSession) -> bool:
        result = await db.execute(
            select(func.count()).select_from(AcadProgram).where(
                AcadProgram.department_id == dept_id,
                AcadProgram.is_active.is_(True),
            )
        )
        return (result.scalar() or 0) > 0


class ProgramRepo:

    @staticmethod
    async def create(
        department_id: UUID,
        name: str,
        code: str,
        degree_type: str,
        duration_years: int,
        db: AsyncSession,
    ) -> AcadProgram:
        prog = AcadProgram(
            department_id=department_id,
            name=name,
            code=code,
            degree_type=degree_type,
            duration_years=duration_years,
        )
        db.add(prog)
        await db.flush()
        await db.refresh(prog)
        return prog

    @staticmethod
    async def get_by_id(prog_id: UUID, db: AsyncSession) -> AcadProgram | None:
        result = await db.execute(select(AcadProgram).where(AcadProgram.id == prog_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_code(code: str, db: AsyncSession) -> AcadProgram | None:
        result = await db.execute(select(AcadProgram).where(AcadProgram.code == code))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession,
        department_id: UUID | None = None,
        include_inactive: bool = False,
    ) -> list[AcadProgram]:
        stmt = select(AcadProgram).order_by(AcadProgram.name)
        if department_id:
            stmt = stmt.where(AcadProgram.department_id == department_id)
        if not include_inactive:
            stmt = stmt.where(AcadProgram.is_active.is_(True))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update(prog: AcadProgram, updates: dict, db: AsyncSession) -> AcadProgram:
        for key, val in updates.items():
            setattr(prog, key, val)
        prog.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(prog)
        return prog

    @staticmethod
    async def has_active_batches(prog_id: UUID, db: AsyncSession) -> bool:
        result = await db.execute(
            select(func.count()).select_from(AcadBatch).where(
                AcadBatch.program_id == prog_id,
                AcadBatch.is_active.is_(True),
            )
        )
        return (result.scalar() or 0) > 0


class BatchRepo:

    @staticmethod
    async def create(
        program_id: UUID,
        name: str,
        start_year: int,
        end_year: int,
        db: AsyncSession,
    ) -> AcadBatch:
        batch = AcadBatch(
            program_id=program_id,
            name=name,
            start_year=start_year,
            end_year=end_year,
        )
        db.add(batch)
        await db.flush()
        await db.refresh(batch)
        return batch

    @staticmethod
    async def get_by_id(batch_id: UUID, db: AsyncSession) -> AcadBatch | None:
        result = await db.execute(select(AcadBatch).where(AcadBatch.id == batch_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_program_and_year(
        program_id: UUID, start_year: int, db: AsyncSession
    ) -> AcadBatch | None:
        result = await db.execute(
            select(AcadBatch).where(
                AcadBatch.program_id == program_id,
                AcadBatch.start_year == start_year,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession,
        program_id: UUID | None = None,
        include_inactive: bool = False,
    ) -> list[AcadBatch]:
        stmt = select(AcadBatch).order_by(AcadBatch.start_year.desc())
        if program_id:
            stmt = stmt.where(AcadBatch.program_id == program_id)
        if not include_inactive:
            stmt = stmt.where(AcadBatch.is_active.is_(True))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update(batch: AcadBatch, updates: dict, db: AsyncSession) -> AcadBatch:
        for key, val in updates.items():
            setattr(batch, key, val)
        batch.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(batch)
        return batch

    @staticmethod
    async def has_active_semesters(batch_id: UUID, db: AsyncSession) -> bool:
        result = await db.execute(
            select(func.count()).select_from(AcadSemester).where(
                AcadSemester.batch_id == batch_id,
                AcadSemester.is_active.is_(True),
            )
        )
        return (result.scalar() or 0) > 0


class SemesterRepo:

    @staticmethod
    async def create(
        batch_id: UUID,
        number: int,
        label: str | None,
        db: AsyncSession,
    ) -> AcadSemester:
        sem = AcadSemester(batch_id=batch_id, number=number, label=label)
        db.add(sem)
        await db.flush()
        await db.refresh(sem)
        return sem

    @staticmethod
    async def get_by_id(sem_id: UUID, db: AsyncSession) -> AcadSemester | None:
        result = await db.execute(select(AcadSemester).where(AcadSemester.id == sem_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_batch_and_number(
        batch_id: UUID, number: int, db: AsyncSession
    ) -> AcadSemester | None:
        result = await db.execute(
            select(AcadSemester).where(
                AcadSemester.batch_id == batch_id,
                AcadSemester.number == number,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession,
        batch_id: UUID | None = None,
        include_inactive: bool = False,
    ) -> list[AcadSemester]:
        stmt = select(AcadSemester).order_by(AcadSemester.number)
        if batch_id:
            stmt = stmt.where(AcadSemester.batch_id == batch_id)
        if not include_inactive:
            stmt = stmt.where(AcadSemester.is_active.is_(True))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update(sem: AcadSemester, updates: dict, db: AsyncSession) -> AcadSemester:
        for key, val in updates.items():
            setattr(sem, key, val)
        await db.flush()
        await db.refresh(sem)
        return sem

    @staticmethod
    async def has_active_sections(sem_id: UUID, db: AsyncSession) -> bool:
        result = await db.execute(
            select(func.count()).select_from(AcadSection).where(
                AcadSection.semester_id == sem_id,
                AcadSection.is_active.is_(True),
            )
        )
        return (result.scalar() or 0) > 0


class SectionRepo:

    @staticmethod
    async def create(
        semester_id: UUID,
        name: str,
        max_strength: int | None,
        db: AsyncSession,
    ) -> AcadSection:
        section = AcadSection(semester_id=semester_id, name=name, max_strength=max_strength)
        db.add(section)
        await db.flush()
        await db.refresh(section)
        return section

    @staticmethod
    async def get_by_id(section_id: UUID, db: AsyncSession) -> AcadSection | None:
        result = await db.execute(select(AcadSection).where(AcadSection.id == section_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_semester_and_name(
        semester_id: UUID, name: str, db: AsyncSession
    ) -> AcadSection | None:
        result = await db.execute(
            select(AcadSection).where(
                AcadSection.semester_id == semester_id,
                AcadSection.name == name,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession,
        semester_id: UUID | None = None,
        include_inactive: bool = False,
    ) -> list[AcadSection]:
        stmt = select(AcadSection).order_by(AcadSection.name)
        if semester_id:
            stmt = stmt.where(AcadSection.semester_id == semester_id)
        if not include_inactive:
            stmt = stmt.where(AcadSection.is_active.is_(True))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update(section: AcadSection, updates: dict, db: AsyncSession) -> AcadSection:
        for key, val in updates.items():
            setattr(section, key, val)
        await db.flush()
        await db.refresh(section)
        return section
