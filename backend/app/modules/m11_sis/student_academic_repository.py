"""
Student academic context — shared enrollment/course/syllabus join helpers.

Single source of truth for "what is this student enrolled in", reused by:
  - m11_sis (My Subjects / Subject Details)
  - m03_course_kit (student course-kit endpoints — ownership check)
  - m05_learning_materials (student package endpoints — ownership check)

acad_enrollments has one active row per student (current section only) — there
is no multi-semester history in this schema yet, so these joins naturally
return the student's *current* subjects. subject_assignments.section_id is
nullable (a semester-wide assignment with no specific section), so the join
matches either the student's exact section or a section-agnostic assignment
for the same semester.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_ASSIGNMENT_JOIN = """
    JOIN subject_assignments sa
      ON sa.is_active = true
     AND (sa.section_id = ae.section_id OR (sa.section_id IS NULL AND sa.semester_id = s.semester_id))
"""


async def get_student_enrolled_course_ids(
    student_id: UUID,
    db: AsyncSession,
    semester_id: UUID | None = None,
) -> set[UUID]:
    """Course IDs the student is currently enrolled in (via active section + subject_assignments)."""
    params: dict = {"student_id": str(student_id)}
    semester_filter = ""
    if semester_id is not None:
        semester_filter = "AND sa.semester_id = :semester_id"
        params["semester_id"] = str(semester_id)

    sql = text(f"""
        SELECT DISTINCT sa.course_id
        FROM acad_enrollments ae
        JOIN acad_sections s ON s.id = ae.section_id
        {_ASSIGNMENT_JOIN}
        WHERE ae.student_id = :student_id
          AND ae.is_active   = true
          {semester_filter}
    """)
    result = await db.execute(sql, params)
    return {row[0] for row in result.fetchall()}


async def get_student_enrolled_syllabus_ids(student_id: UUID, db: AsyncSession) -> set[UUID]:
    """Syllabus IDs (DEAN_APPROVED/DEAN_LOCKED only) for the student's enrolled courses.

    Used as the ownership check for student-facing Course Kit / Learning
    Material access: a kit/package's syllabus_id must be in this set.
    """
    sql = text(f"""
        SELECT DISTINCT syl.id
        FROM acad_enrollments ae
        JOIN acad_sections s ON s.id = ae.section_id
        {_ASSIGNMENT_JOIN}
        JOIN syllabi syl
          ON syl.course_id = sa.course_id
         AND syl.status IN ('DEAN_APPROVED', 'DEAN_LOCKED')
        WHERE ae.student_id = :student_id
          AND ae.is_active   = true
    """)
    result = await db.execute(sql, {"student_id": str(student_id)})
    return {row[0] for row in result.fetchall()}


async def get_student_enrolled_courses_raw(
    student_id: UUID,
    db: AsyncSession,
    semester_id: UUID | None = None,
) -> list[dict]:
    """Full course+faculty+section rows for the student's current subjects (My Subjects list).

    One row per (course, faculty) pair; PRIMARY faculty sorted first so callers
    that want a single faculty per course can just take the first match.
    """
    params: dict = {"student_id": str(student_id)}
    semester_filter = ""
    if semester_id is not None:
        semester_filter = "AND sa.semester_id = :semester_id"
        params["semester_id"] = str(semester_id)

    sql = text(f"""
        SELECT
            c.id              AS course_id,
            c.code            AS course_code,
            c.title           AS course_title,
            c.credits,
            c.semester,
            c.course_type,
            c.is_elective,
            ae.section_id,
            s.name            AS section_name,
            sa.faculty_user_id,
            sa.role_in_course,
            latest_syl.id       AS syllabus_id,
            latest_syl.status   AS syllabus_status
        FROM acad_enrollments ae
        JOIN acad_sections s ON s.id = ae.section_id
        {_ASSIGNMENT_JOIN}
        JOIN courses c ON c.id = sa.course_id
        LEFT JOIN LATERAL (
            SELECT syl.id, syl.status
            FROM syllabi syl
            WHERE syl.course_id = c.id
              AND syl.status IN ('DEAN_APPROVED', 'DEAN_LOCKED')
            ORDER BY syl.version DESC
            LIMIT 1
        ) latest_syl ON true
        WHERE ae.student_id = :student_id
          AND ae.is_active   = true
          {semester_filter}
        ORDER BY c.semester, c.code, CASE WHEN sa.role_in_course = 'PRIMARY' THEN 0 ELSE 1 END
    """)
    result = await db.execute(sql, params)
    return [dict(row) for row in result.mappings().all()]


async def get_student_course_row(
    student_id: UUID,
    course_id: UUID,
    db: AsyncSession,
) -> dict | None:
    """Single course + section + primary-faculty row for one enrolled course.

    Returns None if the student isn't enrolled in / assigned to this course —
    the caller should treat that as a 404.
    """
    sql = text(f"""
        SELECT
            c.id              AS course_id,
            c.code            AS course_code,
            c.title           AS course_title,
            c.credits,
            c.semester,
            c.course_type,
            c.is_elective,
            c.description,
            c.hours_lecture,
            c.hours_tutorial,
            c.hours_practical,
            ae.section_id,
            s.name            AS section_name,
            sa.faculty_user_id,
            sa.role_in_course
        FROM acad_enrollments ae
        JOIN acad_sections s ON s.id = ae.section_id
        {_ASSIGNMENT_JOIN}
        JOIN courses c ON c.id = sa.course_id
        WHERE ae.student_id = :student_id
          AND ae.is_active   = true
          AND sa.course_id   = :course_id
        ORDER BY CASE WHEN sa.role_in_course = 'PRIMARY' THEN 0 ELSE 1 END
        LIMIT 1
    """)
    result = await db.execute(sql, {"student_id": str(student_id), "course_id": str(course_id)})
    row = result.mappings().first()
    return dict(row) if row is not None else None
