"""Shared DEAN program-scope helper (Phase 2 refinements).

Every module that lists or reads program-attributable data (programs,
syllabuses, course kits, learning packages, faculty/course assignments,
faculty/student directory, attendance analytics) must filter DEAN-role
callers down to only the programs they govern, per `dean_program_assignments`
(see `m_academics/ownership_service.py`, the original — and until now, only
— correctly-scoped consumer of that table).

This helper is the single source of truth for resolving "which acad_programs
does this caller govern" so every module applies the exact same rule.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

UNRESTRICTED_ROLES = ("ADMIN", "SUPER_ADMIN")


async def get_semester_program_id(semester_id: UUID, db: AsyncSession) -> UUID | None:
    """Resolve one semester's program_id via semester -> batch -> program.

    Mirrors `core/timetable/dean_scope.py`'s `get_section_program_id` (same
    join style, one level shorter since a semester already sits above section
    in the acad_* hierarchy) -- used to scope Dean-owned resources that are
    keyed by semester_id rather than section_id (e.g. elective offerings).
    """
    row = (
        await db.execute(
            text(
                "SELECT b.program_id "
                "FROM acad_semesters sem "
                "JOIN acad_batches b ON b.id = sem.batch_id "
                "WHERE sem.id = :semester_id"
            ),
            {"semester_id": str(semester_id)},
        )
    ).scalar_one_or_none()
    return row


async def assert_dean_owns_semester_program(
    dean_user_id: UUID, semester_id: UUID, db: AsyncSession, not_found_message: str
) -> None:
    """Raise a 404-shaped AcadServiceError if the semester's program isn't
    governed by this dean. Mirrors `core/timetable/dean_scope.py`'s
    `assert_dean_owns_section` exactly -- 404, not 403, so an out-of-scope
    resource doesn't leak its existence to a dean who shouldn't see it."""
    from app.modules.m_academics.service import AcadServiceError

    program_ids = await get_dean_program_ids(dean_user_id, "DEAN", db)
    semester_program_id = await get_semester_program_id(semester_id, db)
    if not program_ids or semester_program_id is None or semester_program_id not in program_ids:
        raise AcadServiceError("NOT_FOUND", not_found_message, 404)


async def get_dean_program_ids(
    user_id: UUID, role: str, db: AsyncSession
) -> list[UUID] | None:
    """Return the acad_programs.id values `user_id` governs.

    Returns:
      - ``None``       -> unrestricted (ADMIN / SUPER_ADMIN) — caller must
                           skip filtering entirely, not treat this as "no
                           programs".
      - ``list[UUID]``  -> the (possibly empty) set of governed programs for
                           a DEAN. An empty list means the dean governs
                           nothing and callers MUST filter results down to
                           nothing (an empty IN-list), never fall back to
                           "unrestricted".

    Every returned UUID is an ``acad_programs.id`` (the institutional
    program registry). Callers whose local `program_id` lives in a
    different table (e.g. the curriculum-design `programs` table in
    `m01_program_advisor`, which links via a nullable `acad_program_id`
    FK) must bridge through that FK before comparing — comparing a local
    `programs.id` directly against this helper's output will silently
    return empty results for every dean.
    """
    if role in UNRESTRICTED_ROLES:
        return None

    rows = (
        await db.execute(
            text(
                "SELECT program_id FROM dean_program_assignments "
                "WHERE dean_user_id = :uid AND is_active = true"
            ),
            {"uid": str(user_id)},
        )
    ).scalars().all()
    return list(rows)
