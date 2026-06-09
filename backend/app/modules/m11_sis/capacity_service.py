"""Enrollment Capacity Engine — H64.6.

Reads max_strength from acad_sections and counts active enrollments to
produce capacity snapshots.  Also used by enrollment_service to gate
new enrollments when a cap is set.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m_academics.models import AcadEnrollment, AcadSection, AcadSemester
from app.modules.m11_sis.capacity_schemas import SectionCapacityOut


class CapacityError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _build_out(section: AcadSection, enrolled: int) -> SectionCapacityOut:
    ms = section.max_strength
    available = (ms - enrolled) if ms is not None else None
    is_full   = ms is not None and enrolled >= ms
    fill_pct  = round((enrolled / ms) * 100, 1) if ms else None
    return SectionCapacityOut(
        section_id=section.id,
        section_name=section.name,
        semester_id=section.semester_id,
        max_strength=ms,
        enrolled=enrolled,
        available=available,
        is_full=is_full,
        fill_pct=fill_pct,
    )


class CapacityService:

    @staticmethod
    async def get_section_capacity(section_id: UUID, *, db: AsyncSession) -> SectionCapacityOut:
        section = (
            await db.execute(select(AcadSection).where(AcadSection.id == section_id))
        ).scalar_one_or_none()
        if section is None:
            raise CapacityError("SECTION_NOT_FOUND", "Section not found.", 404)

        count = (
            await db.execute(
                select(func.count()).where(
                    AcadEnrollment.section_id == section_id,
                    AcadEnrollment.is_active.is_(True),
                )
            )
        ).scalar_one()
        return _build_out(section, count)

    @staticmethod
    async def list_sections_capacity(
        *,
        semester_id: Optional[UUID] = None,
        db: AsyncSession,
    ) -> list[SectionCapacityOut]:
        stmt = select(AcadSection)
        if semester_id is not None:
            stmt = stmt.where(AcadSection.semester_id == semester_id)
        stmt = stmt.order_by(AcadSection.name)
        sections = (await db.execute(stmt)).scalars().all()
        if not sections:
            return []

        section_ids = [s.id for s in sections]
        counts_rows = (
            await db.execute(
                select(AcadEnrollment.section_id, func.count().label("cnt"))
                .where(
                    AcadEnrollment.section_id.in_(section_ids),
                    AcadEnrollment.is_active.is_(True),
                )
                .group_by(AcadEnrollment.section_id)
            )
        ).all()
        count_map = {row.section_id: row.cnt for row in counts_rows}

        return [_build_out(s, count_map.get(s.id, 0)) for s in sections]

    @staticmethod
    async def set_capacity(
        section_id: UUID,
        max_strength: Optional[int],
        *,
        db: AsyncSession,
    ) -> SectionCapacityOut:
        section = (
            await db.execute(select(AcadSection).where(AcadSection.id == section_id))
        ).scalar_one_or_none()
        if section is None:
            raise CapacityError("SECTION_NOT_FOUND", "Section not found.", 404)

        # Safety: don't allow setting cap below current enrollment
        if max_strength is not None:
            enrolled = (
                await db.execute(
                    select(func.count()).where(
                        AcadEnrollment.section_id == section_id,
                        AcadEnrollment.is_active.is_(True),
                    )
                )
            ).scalar_one()
            if enrolled > max_strength:
                raise CapacityError(
                    "BELOW_CURRENT_ENROLLMENT",
                    f"Cannot set capacity to {max_strength}; section already has {enrolled} active enrollments.",
                    409,
                )

        section.max_strength = max_strength
        await db.flush()

        count = (
            await db.execute(
                select(func.count()).where(
                    AcadEnrollment.section_id == section_id,
                    AcadEnrollment.is_active.is_(True),
                )
            )
        ).scalar_one()
        return _build_out(section, count)

    @staticmethod
    async def check_capacity(section_id: UUID, *, db: AsyncSession) -> None:
        """Raises CapacityError(409) if the section is at or over its cap."""
        section = (
            await db.execute(select(AcadSection).where(AcadSection.id == section_id))
        ).scalar_one_or_none()
        if section is None or section.max_strength is None:
            return  # no cap set — nothing to check

        enrolled = (
            await db.execute(
                select(func.count()).where(
                    AcadEnrollment.section_id == section_id,
                    AcadEnrollment.is_active.is_(True),
                )
            )
        ).scalar_one()
        if enrolled >= section.max_strength:
            raise CapacityError(
                "SECTION_AT_CAPACITY",
                f"Section is at capacity ({enrolled}/{section.max_strength}).",
                409,
            )
