from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m11_sis.models import SisSchool
from app.modules.m_academics.models import AcadDepartment


class SchoolRepository:

    @staticmethod
    async def list_all(db: AsyncSession, include_inactive: bool = False) -> list[SisSchool]:
        stmt = select(SisSchool).order_by(SisSchool.name)
        if not include_inactive:
            stmt = stmt.where(SisSchool.is_active.is_(True))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(school_id: UUID, db: AsyncSession) -> SisSchool | None:
        result = await db.execute(select(SisSchool).where(SisSchool.id == school_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_code(code: str, db: AsyncSession) -> SisSchool | None:
        result = await db.execute(select(SisSchool).where(SisSchool.code == code))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_name(name: str, db: AsyncSession) -> SisSchool | None:
        result = await db.execute(select(SisSchool).where(SisSchool.name == name))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(code: str, name: str, description: str | None, db: AsyncSession) -> SisSchool:
        school = SisSchool(code=code, name=name, description=description)
        db.add(school)
        await db.flush()
        await db.refresh(school)
        return school

    @staticmethod
    async def update(school: SisSchool, updates: dict, db: AsyncSession) -> SisSchool:
        for key, val in updates.items():
            setattr(school, key, val)
        school.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(school)
        return school

    @staticmethod
    async def count_departments(school_id: UUID, db: AsyncSession) -> int:
        result = await db.execute(
            select(func.count()).select_from(AcadDepartment).where(
                AcadDepartment.school_id == school_id
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def delete(school: SisSchool, db: AsyncSession) -> None:
        await db.delete(school)
        await db.flush()
