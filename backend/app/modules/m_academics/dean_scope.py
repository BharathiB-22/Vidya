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
