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

from app.modules.m_academics.models import (
    AcadBatch,
    AcadDepartment,
    AcadEnrollment,
    AcadProgram,
    AcadSection,
    AcadSemester,
)
from app.modules.m11_sis.capacity_schemas import SectionCapacityOut
from app.modules.m11_sis.models import SisSchool


class CapacityError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _status(ms: Optional[int], enrolled: int) -> str:
    """Derive a status bucket from capacity and current enrollment.

    NO_CAP    — no cap configured
    OVER      — enrolled exceeds cap (over capacity)
    FULL      — enrolled == cap (100%)
    NEAR_FULL — fill rate strictly above 80%
    HEALTHY   — everything else
    """
    if ms is None:
        return "NO_CAP"
    if enrolled > ms:
        return "OVER"
    if enrolled == ms:
        return "FULL"
    if (enrolled / ms) * 100 > 80:
        return "NEAR_FULL"
    return "HEALTHY"


def _build_out(section: AcadSection, enrolled: int, ctx: Optional[dict] = None) -> SectionCapacityOut:
    ms = section.max_strength
    available = (ms - enrolled) if ms is not None else None
    is_full   = ms is not None and enrolled >= ms
    fill_pct  = round((enrolled / ms) * 100, 1) if ms else None
    ctx = ctx or {}
    return SectionCapacityOut(
        section_id=section.id,
        section_name=section.name,
        semester_id=section.semester_id,
        max_strength=ms,
        enrolled=enrolled,
        available=available,
        is_full=is_full,
        fill_pct=fill_pct,
        status=_status(ms, enrolled),
        **ctx,
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
        # Join the full academic hierarchy so each section carries its
        # School / Department / Program / Batch / Semester context.
        stmt = (
            select(
                AcadSection,
                AcadSemester.number.label("sem_number"),
                AcadSemester.label.label("sem_label"),
                AcadBatch.id.label("batch_id"),
                AcadBatch.name.label("batch_name"),
                AcadBatch.start_year.label("batch_start_year"),
                AcadProgram.id.label("program_id"),
                AcadProgram.name.label("program_name"),
                AcadProgram.code.label("program_code"),
                AcadDepartment.id.label("department_id"),
                AcadDepartment.name.label("department_name"),
                SisSchool.id.label("school_id"),
                SisSchool.name.label("school_name"),
            )
            .join(AcadSemester, AcadSection.semester_id == AcadSemester.id)
            .join(AcadBatch, AcadSemester.batch_id == AcadBatch.id)
            .join(AcadProgram, AcadBatch.program_id == AcadProgram.id)
            .join(AcadDepartment, AcadProgram.department_id == AcadDepartment.id)
            .outerjoin(SisSchool, AcadDepartment.school_id == SisSchool.id)
        )
        if semester_id is not None:
            stmt = stmt.where(AcadSection.semester_id == semester_id)
        stmt = stmt.order_by(
            SisSchool.name, AcadProgram.name, AcadBatch.start_year,
            AcadSemester.number, AcadSection.name,
        )
        rows = (await db.execute(stmt)).all()
        if not rows:
            return []

        sections = [r[0] for r in rows]
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

        out: list[SectionCapacityOut] = []
        for r in rows:
            section = r[0]
            ctx = {
                "school_id":       r.school_id,
                "school_name":     r.school_name,
                "department_id":   r.department_id,
                "department_name": r.department_name,
                "program_id":      r.program_id,
                "program_name":    r.program_name,
                "program_code":    r.program_code,
                "batch_id":        r.batch_id,
                "batch_name":      r.batch_name,
                "semester_number": r.sem_number,
                "semester_label":  r.sem_label,
            }
            out.append(_build_out(section, count_map.get(section.id, 0), ctx))
        return out

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
