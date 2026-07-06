"""Dean department/section scoping for the Timetable module (Phase 4.1).

Reuses the canonical `get_dean_program_ids` helper (m_academics.dean_scope) —
the single source of truth for "which acad_programs does this dean govern".
Everything here is a thin derivation on top of it; no duplicate query logic.

House style: an out-of-scope resource returns 404 (not 403) to avoid leaking
existence, matching m11_sis's dean-scoped directory endpoints.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m_academics.dean_scope import get_dean_program_ids


async def get_dean_department_ids(dean_user_id: UUID, db: AsyncSession) -> list[UUID]:
    """Departments the dean governs, derived from their governed programs."""
    program_ids = await get_dean_program_ids(dean_user_id, "DEAN", db)
    if not program_ids:
        return []
    rows = (
        await db.execute(
            text("SELECT DISTINCT department_id FROM acad_programs WHERE id = ANY(:ids)"),
            {"ids": [str(p) for p in program_ids]},
        )
    ).scalars().all()
    return list(rows)


async def get_dean_section_ids(dean_user_id: UUID, db: AsyncSession) -> list[UUID]:
    """All acad_sections.id belonging to any program the dean governs."""
    program_ids = await get_dean_program_ids(dean_user_id, "DEAN", db)
    if not program_ids:
        return []
    rows = (
        await db.execute(
            text("""
                SELECT sec.id
                FROM acad_sections  sec
                JOIN acad_semesters sem ON sem.id = sec.semester_id
                JOIN acad_batches   b   ON b.id  = sem.batch_id
                WHERE b.program_id = ANY(:ids)
            """),
            {"ids": [str(p) for p in program_ids]},
        )
    ).scalars().all()
    return list(rows)


async def get_section_program_id(section_id: UUID, db: AsyncSession) -> UUID | None:
    """Resolve one section's program_id via section -> semester -> batch -> program."""
    row = (
        await db.execute(
            text("""
                SELECT b.program_id
                FROM acad_sections  sec
                JOIN acad_semesters sem ON sem.id = sec.semester_id
                JOIN acad_batches   b   ON b.id  = sem.batch_id
                WHERE sec.id = :section_id
            """),
            {"section_id": str(section_id)},
        )
    ).scalar_one_or_none()
    return row


async def get_section_department_id(section_id: UUID, db: AsyncSession) -> UUID | None:
    """Resolve one section's department_id via its program."""
    row = (
        await db.execute(
            text("""
                SELECT ap.department_id
                FROM acad_sections  sec
                JOIN acad_semesters sem ON sem.id = sec.semester_id
                JOIN acad_batches   b   ON b.id  = sem.batch_id
                JOIN acad_programs  ap  ON ap.id  = b.program_id
                WHERE sec.id = :section_id
            """),
            {"section_id": str(section_id)},
        )
    ).scalar_one_or_none()
    return row


async def assert_dean_owns_section(dean_user_id: UUID, section_id: UUID, db: AsyncSession) -> None:
    """Raise a 404-shaped TimetableServiceError if the section's program isn't governed."""
    from app.core.timetable.service import TimetableServiceError  # local import: avoids a circular import

    program_ids = await get_dean_program_ids(dean_user_id, "DEAN", db)
    section_program_id = await get_section_program_id(section_id, db)
    if not program_ids or section_program_id is None or section_program_id not in program_ids:
        raise TimetableServiceError("NOT_FOUND", "Timetable not found.", 404)


async def assert_dean_owns_department(dean_user_id: UUID, department_id: UUID, db: AsyncSession) -> None:
    """Raise a 404-shaped TimetableServiceError if the department isn't governed."""
    from app.core.timetable.service import TimetableServiceError  # local import: avoids a circular import

    department_ids = await get_dean_department_ids(dean_user_id, db)
    if department_id not in department_ids:
        raise TimetableServiceError("NOT_FOUND", "Department not found.", 404)
