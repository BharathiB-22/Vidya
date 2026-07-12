"""Who is in this class?

There are exactly two kinds of class in Vidya, and every roster read must go
through here so they stay consistent:

  **Section class** — a regular course taught to one section. Its roster is the
  section's active enrolments.

  **Elective group** — one option course inside an elective slot, taught to
  everyone in a term who chose it. MCA-A's 20 students and MCA-B's 15 who both
  picked Artificial Intelligence form ONE class of 35. The roster is the
  elective registrations for `(course_id, semester_id)` and mentions no section
  at all — which is precisely why the combined class falls out for free.

Attendance and internal marks both call `resolve_class_roster`, so a student
cannot appear in one and be missing from the other.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def is_elective_course(course_id: UUID, db: AsyncSession) -> bool:
    """True when the course is an option inside an elective slot.

    `is_elective` alone is not sufficient history: older rows were tagged
    elective without belonging to a basket. Either marker counts.
    """
    row = (await db.execute(text("""
        SELECT (is_elective OR elective_basket_id IS NOT NULL) AS is_elective
        FROM courses WHERE id = :course_id
    """), {"course_id": str(course_id)})).scalar_one_or_none()
    return bool(row)


async def get_elective_group_student_ids(
    course_id: UUID, semester_id: UUID, db: AsyncSession,
) -> list[UUID]:
    """Every student in `semester_id` who chose `course_id` — across all
    sections. No section filter: that is the whole point of a combined class."""
    rows = (await db.execute(text("""
        SELECT er.student_user_id
        FROM elective_registrations er
        WHERE er.course_id   = :course_id
          AND er.semester_id = :semester_id
          AND er.status      = 'REGISTERED'
        ORDER BY er.student_user_id
    """), {"course_id": str(course_id), "semester_id": str(semester_id)})).scalars().all()
    return [UUID(str(r)) for r in rows]


async def get_section_student_ids(section_id: UUID, db: AsyncSession) -> list[UUID]:
    rows = (await db.execute(text("""
        SELECT ae.student_id
        FROM acad_enrollments ae
        WHERE ae.section_id = :section_id AND ae.is_active = true
        ORDER BY ae.student_id
    """), {"section_id": str(section_id)})).scalars().all()
    return [UUID(str(r)) for r in rows]


async def resolve_class_roster(
    course_id: UUID,
    semester_id: UUID,
    section_id: UUID | None,
    db: AsyncSession,
) -> list[UUID]:
    """The single entry point. `section_id is None` means the elective group.

    Callers should pass `section_id=None` for an elective course and the section
    for everything else; `is_elective_course` decides which they are.
    """
    if section_id is None:
        return await get_elective_group_student_ids(course_id, semester_id, db)
    return await get_section_student_ids(section_id, db)
