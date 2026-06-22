"""
SIS Directory Repository — H50.

Handles paginated queries for student and faculty directories,
plus profile upsert operations for both entity types.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.models import TenantRole, User
from app.modules.m01_program_advisor.models import Course
from app.modules.m11_sis.models import SisFacultyProfile, SisStudentProfile
from app.modules.m_academics.models import (
    AcadBatch,
    AcadDepartment,
    AcadEnrollment,
    AcadProgram,
    AcadSection,
    AcadSemester,
    FacultyProgramAssignment,
    FacultyRoleGrant,
    SubjectAssignment,
)


def _faculty_in_department(department_id):
    """Department-membership predicate for a faculty row.

    Uses a non-correlated IN subquery rather than a correlated EXISTS so the
    predicate survives being wrapped in a count subquery
    (``select(func.count()).select_from(stmt.subquery())``).
    """
    via_assignment = (
        select(FacultyProgramAssignment.faculty_user_id)
        .join(AcadProgram, AcadProgram.id == FacultyProgramAssignment.program_id)
        .where(
            FacultyProgramAssignment.is_active.is_(True),
            AcadProgram.department_id == department_id,
        )
    )
    return or_(
        SisFacultyProfile.primary_department_id == department_id,
        User.id.in_(via_assignment),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _student_base_stmt():
    """Core SELECT joining users → profile → program → dept → enrollment → section."""
    return (
        select(
            User,
            SisStudentProfile,
            AcadProgram,
            AcadDepartment,
            AcadBatch,
            AcadSection,
        )
        .where(User.role == TenantRole.STUDENT)
        .outerjoin(SisStudentProfile, SisStudentProfile.user_id == User.id)
        .outerjoin(AcadProgram, AcadProgram.id == User.acad_program_id)
        .outerjoin(AcadDepartment, AcadDepartment.id == AcadProgram.department_id)
        .outerjoin(
            AcadEnrollment,
            and_(AcadEnrollment.student_id == User.id, AcadEnrollment.is_active.is_(True)),
        )
        .outerjoin(AcadSection, AcadSection.id == AcadEnrollment.section_id)
        .outerjoin(AcadSemester, AcadSemester.id == AcadSection.semester_id)
        .outerjoin(AcadBatch, AcadBatch.id == AcadSemester.batch_id)
    )


_LEGACY_GOVERNANCE_ROLES = ("BOARD", "DEAN")


def _faculty_base_stmt():
    """Core SELECT joining users → profile → primary_department.

    Excludes pre-Phase-1.7 accounts that have ``users.role=FACULTY`` but
    hold an active BOARD or DEAN grant — those are governance users who were
    mis-imported before BOARD/DEAN became primary roles.  After running
    ``scripts/repair_board_dean_roles.py`` this subquery returns an empty
    set and has zero cost.
    """
    legacy_ids = (
        select(FacultyRoleGrant.faculty_user_id)
        .where(
            FacultyRoleGrant.role_code.in_(_LEGACY_GOVERNANCE_ROLES),
            FacultyRoleGrant.is_active.is_(True),
        )
    )
    return (
        select(User, SisFacultyProfile, AcadDepartment)
        .where(User.role == TenantRole.FACULTY)
        .where(User.id.not_in(legacy_ids))
        .outerjoin(SisFacultyProfile, SisFacultyProfile.user_id == User.id)
        .outerjoin(AcadDepartment, AcadDepartment.id == SisFacultyProfile.primary_department_id)
    )


# ---------------------------------------------------------------------------
# Student repository
# ---------------------------------------------------------------------------

class StudentDirectoryRepository:

    @staticmethod
    async def list_paginated(
        db: AsyncSession,
        *,
        page: int,
        page_size: int,
        search: str | None,
        program_id: UUID | None,
        batch_id: UUID | None,
        section_id: UUID | None,
        is_active: bool | None,
    ) -> tuple[list[Any], int]:
        stmt = _student_base_stmt()

        if search:
            pattern = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(User.full_name).like(pattern),
                    func.lower(User.email).like(pattern),
                    func.lower(SisStudentProfile.usn).like(pattern),
                )
            )
        if program_id is not None:
            stmt = stmt.where(User.acad_program_id == program_id)
        if batch_id is not None:
            stmt = stmt.where(AcadBatch.id == batch_id)
        if section_id is not None:
            stmt = stmt.where(AcadSection.id == section_id)
        if is_active is not None:
            stmt = stmt.where(User.is_active.is_(is_active))

        # Count before pagination
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(User.full_name).offset((page - 1) * page_size).limit(page_size)
        rows = (await db.execute(stmt)).all()
        return rows, total

    @staticmethod
    async def get_by_user_id(user_id: UUID, db: AsyncSession) -> Any | None:
        stmt = _student_base_stmt().where(User.id == user_id)
        result = await db.execute(stmt)
        return result.first()

    @staticmethod
    async def upsert_profile(
        user_id: UUID,
        updates: dict,
        db: AsyncSession,
    ) -> SisStudentProfile:
        result = await db.execute(
            select(SisStudentProfile).where(SisStudentProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if profile is None:
            profile = SisStudentProfile(user_id=user_id, **updates)
            db.add(profile)
        else:
            for k, v in updates.items():
                setattr(profile, k, v)
            profile.updated_at = now
        await db.flush()
        await db.refresh(profile)
        return profile

    @staticmethod
    async def get_profile(user_id: UUID, db: AsyncSession) -> SisStudentProfile | None:
        result = await db.execute(
            select(SisStudentProfile).where(SisStudentProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Faculty repository
# ---------------------------------------------------------------------------

class FacultyDirectoryRepository:

    @staticmethod
    async def list_paginated(
        db: AsyncSession,
        *,
        page: int,
        page_size: int,
        search: str | None,
        department_id: UUID | None,
        is_active: bool | None,
    ) -> tuple[list[Any], int]:
        stmt = _faculty_base_stmt()

        if search:
            pattern = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(User.full_name).like(pattern),
                    func.lower(User.email).like(pattern),
                    func.lower(SisFacultyProfile.employee_id).like(pattern),
                )
            )
        if department_id is not None:
            stmt = stmt.where(_faculty_in_department(department_id))
        if is_active is not None:
            stmt = stmt.where(User.is_active.is_(is_active))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(User.full_name).offset((page - 1) * page_size).limit(page_size)
        rows = (await db.execute(stmt)).all()
        return rows, total

    @staticmethod
    async def get_by_user_id(user_id: UUID, db: AsyncSession) -> Any | None:
        stmt = _faculty_base_stmt().where(User.id == user_id)
        result = await db.execute(stmt)
        return result.first()

    @staticmethod
    async def get_active_assignments(
        user_id: UUID, db: AsyncSession
    ) -> list[Any]:
        stmt = (
            select(SubjectAssignment, Course, AcadSemester)
            .where(
                SubjectAssignment.faculty_user_id == user_id,
                SubjectAssignment.is_active.is_(True),
            )
            .outerjoin(Course, Course.id == SubjectAssignment.course_id)
            .outerjoin(AcadSemester, AcadSemester.id == SubjectAssignment.semester_id)
            .order_by(AcadSemester.number)
        )
        result = await db.execute(stmt)
        return list(result.all())

    @staticmethod
    async def list_by_department(
        department_id: UUID, db: AsyncSession
    ) -> tuple[list[Any], int]:
        stmt = _faculty_base_stmt().where(_faculty_in_department(department_id))
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0
        rows = (await db.execute(stmt.order_by(User.full_name))).all()
        return rows, total

    @staticmethod
    async def upsert_profile(
        user_id: UUID,
        updates: dict,
        db: AsyncSession,
    ) -> SisFacultyProfile:
        result = await db.execute(
            select(SisFacultyProfile).where(SisFacultyProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if profile is None:
            profile = SisFacultyProfile(user_id=user_id, **updates)
            db.add(profile)
        else:
            for k, v in updates.items():
                setattr(profile, k, v)
            profile.updated_at = now
        await db.flush()
        await db.refresh(profile)
        return profile

    @staticmethod
    async def get_profile(user_id: UUID, db: AsyncSession) -> SisFacultyProfile | None:
        result = await db.execute(
            select(SisFacultyProfile).where(SisFacultyProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()
