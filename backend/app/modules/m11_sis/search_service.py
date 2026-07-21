"""Global Search Service — H64.7.

Searches students, faculty, sections, and courses in one round-trip.
Results are capped at PER_KIND items per category.

RBAC filtering:
  ADMIN / DEAN  — all four categories
  FACULTY       — students + sections + courses  (no faculty directory)
  STUDENT       — sections + courses only
"""
from __future__ import annotations


from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.models import TenantRole, User
from app.modules.m01_program_advisor.models import Course
from app.modules.m_academics.models import AcadSection
from app.modules.m11_sis.models import SisFacultyProfile, SisStudentProfile
from app.modules.m11_sis.search_schemas import (
    CourseHit,
    FacultyHit,
    SearchResultsOut,
    SectionHit,
    StudentHit,
)

PER_KIND = 6
MIN_LEN  = 2


async def global_search(
    q: str,
    *,
    actor_role: str,
    db: AsyncSession,
) -> SearchResultsOut:
    q = q.strip()
    if len(q) < MIN_LEN:
        return SearchResultsOut(query=q, students=[], faculty=[], sections=[], courses=[])

    pattern = f"%{q}%"
    can_see_students = actor_role in (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.FACULTY)
    can_see_faculty  = actor_role in (TenantRole.ADMIN, TenantRole.DEAN)
    can_see_sections = True
    can_see_courses  = True

    # ── Students ────────────────────────────────────────────────────────────
    students: list[StudentHit] = []
    if can_see_students:
        rows = (
            await db.execute(
                select(
                    User.id,
                    User.full_name,
                    User.email,
                    User.is_active,
                    SisStudentProfile.usn,
                )
                .outerjoin(SisStudentProfile, SisStudentProfile.user_id == User.id)
                .where(
                    User.role == TenantRole.STUDENT,
                    or_(
                        User.full_name.ilike(pattern),
                        User.email.ilike(pattern),
                        User.identifier.ilike(pattern),
                        SisStudentProfile.usn.ilike(pattern),
                    ),
                )
                .order_by(User.full_name)
                .limit(PER_KIND)
            )
        ).all()
        students = [
            StudentHit(
                id=r.id,
                full_name=r.full_name,
                email=r.email,
                usn=r.usn,
                is_active=r.is_active,
            )
            for r in rows
        ]

    # ── Faculty ─────────────────────────────────────────────────────────────
    faculty: list[FacultyHit] = []
    if can_see_faculty:
        rows = (
            await db.execute(
                select(
                    User.id,
                    User.full_name,
                    User.email,
                    User.is_active,
                    SisFacultyProfile.employee_id,
                )
                .outerjoin(SisFacultyProfile, SisFacultyProfile.user_id == User.id)
                .where(
                    User.role == TenantRole.FACULTY,
                    or_(
                        User.full_name.ilike(pattern),
                        User.email.ilike(pattern),
                        SisFacultyProfile.employee_id.ilike(pattern),
                    ),
                )
                .order_by(User.full_name)
                .limit(PER_KIND)
            )
        ).all()
        faculty = [
            FacultyHit(
                id=r.id,
                full_name=r.full_name,
                email=r.email,
                employee_id=r.employee_id,
                is_active=r.is_active,
            )
            for r in rows
        ]

    # ── Sections ─────────────────────────────────────────────────────────────
    sections: list[SectionHit] = []
    if can_see_sections:
        rows = (
            await db.execute(
                select(AcadSection.id, AcadSection.name, AcadSection.is_active)
                .where(AcadSection.name.ilike(pattern))
                .order_by(AcadSection.name)
                .limit(PER_KIND)
            )
        ).all()
        sections = [SectionHit(id=r.id, name=r.name, is_active=r.is_active) for r in rows]

    # ── Courses ──────────────────────────────────────────────────────────────
    courses: list[CourseHit] = []
    if can_see_courses:
        rows = (
            await db.execute(
                select(Course.id, Course.code, Course.title)
                .where(or_(Course.title.ilike(pattern), Course.code.ilike(pattern)))
                .order_by(Course.title)
                .limit(PER_KIND)
            )
        ).all()
        courses = [CourseHit(id=r.id, code=r.code, title=r.title) for r in rows]

    return SearchResultsOut(
        query=q,
        students=students,
        faculty=faculty,
        sections=sections,
        courses=courses,
    )
