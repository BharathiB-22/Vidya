"""Shared FACULTY ownership guard — the faculty mirror of `dean_scope.py`.

A DEAN is scoped to the programmes they govern; a FACULTY is scoped to the
courses they are actively assigned to teach. Several modules expose detail- and
write-by-id endpoints that a faculty can reach (syllabus, learning packages,
section attendance analytics), and each one must answer the same question before
returning or mutating another owner's data: *does this faculty actually teach
this?* Answering it in one place is what stops the next such endpoint from
leaking for the same reason a previous one did.

These are predicates, not raisers. Each caller raises its own module's error
type (SyllabusServiceError, AttendanceServiceError, ...) so this helper stays
free of cross-module error imports. The predicate reuses
`SubjectAssignmentRepository.get_active_for_faculty_course` — already the
ownership oracle M02/M03/M05 gate writes on — so "teaches" means exactly the same
thing everywhere.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def faculty_teaches_course(
    faculty_user_id: UUID, course_id: UUID, db: AsyncSession
) -> bool:
    """True when the faculty holds an active assignment for this course.

    Role-agnostic: assignments are the single source of truth for who teaches a
    course, regardless of PRIMARY/CO_FACULTY. Callers apply this only to FACULTY
    actors; ADMIN and DEAN keep their own (broader) scope.
    """
    from app.modules.m_academics.assignment_repository import SubjectAssignmentRepository

    assignment = await SubjectAssignmentRepository.get_active_for_faculty_course(
        course_id, faculty_user_id, db=db
    )
    return assignment is not None


async def faculty_teaches_in_section(
    faculty_user_id: UUID, section_id: UUID, db: AsyncSession
) -> bool:
    """True when the faculty teaches at least one course in this section's term.

    Attendance analytics are per-section, and a section belongs to one semester;
    a faculty may see the section's figures only if they teach something in that
    semester. Kept deliberately as "teaches in the section's semester" rather
    than "has a slot in this section", because an elective's combined class has
    no section of its own yet still concerns these students.
    """
    row = (await db.execute(text("""
        SELECT 1
        FROM acad_sections sec
        JOIN subject_assignments sa
             ON sa.semester_id = sec.semester_id
            AND sa.faculty_user_id = :faculty_id
            AND sa.is_active = true
        WHERE sec.id = :section_id
        LIMIT 1
    """), {"faculty_id": str(faculty_user_id), "section_id": str(section_id)})).first()
    return row is not None
