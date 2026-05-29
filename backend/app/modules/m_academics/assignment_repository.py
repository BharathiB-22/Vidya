"""Subject Assignment — repository layer (H-31).

Pure DB access.  No business logic.  All constraint checking lives in service.
"""
from __future__ import annotations

import uuid as _uuid
from uuid import UUID

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m_academics.models import CourseRoleInCourse, SubjectAssignment


class SubjectAssignmentRepository:

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        course_id: UUID,
        faculty_user_id: UUID,
        semester_id: UUID,
        role_in_course: CourseRoleInCourse,
        assigned_by_user_id: UUID,
        *,
        db: AsyncSession,
    ) -> SubjectAssignment:
        row = SubjectAssignment(
            id=_uuid.uuid4(),
            course_id=course_id,
            faculty_user_id=faculty_user_id,
            semester_id=semester_id,
            role_in_course=role_in_course,
            assigned_by_user_id=assigned_by_user_id,
            is_active=True,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return row

    @staticmethod
    async def revoke(
        assignment_id: UUID,
        revoked_by_user_id: UUID,
        *,
        db: AsyncSession,
    ) -> SubjectAssignment | None:
        stmt = (
            update(SubjectAssignment)
            .where(SubjectAssignment.id == assignment_id)
            .values(
                is_active=False,
                revoked_at=func.now(),
                revoked_by_user_id=revoked_by_user_id,
            )
            .returning(SubjectAssignment)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        assignment_id: UUID,
        *,
        db: AsyncSession,
    ) -> SubjectAssignment | None:
        stmt = select(SubjectAssignment).where(SubjectAssignment.id == assignment_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_course(
        course_id: UUID,
        *,
        semester_id: UUID | None = None,
        include_inactive: bool = False,
        db: AsyncSession,
    ) -> list[SubjectAssignment]:
        conditions = [SubjectAssignment.course_id == course_id]
        if semester_id is not None:
            conditions.append(SubjectAssignment.semester_id == semester_id)
        if not include_inactive:
            conditions.append(SubjectAssignment.is_active.is_(True))
        stmt = (
            select(SubjectAssignment)
            .where(and_(*conditions))
            .order_by(SubjectAssignment.assigned_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_by_faculty(
        faculty_user_id: UUID,
        *,
        include_inactive: bool = False,
        db: AsyncSession,
    ) -> list[SubjectAssignment]:
        conditions = [SubjectAssignment.faculty_user_id == faculty_user_id]
        if not include_inactive:
            conditions.append(SubjectAssignment.is_active.is_(True))
        stmt = (
            select(SubjectAssignment)
            .where(and_(*conditions))
            .order_by(SubjectAssignment.assigned_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_active_primary(
        course_id: UUID,
        semester_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(SubjectAssignment.id)).where(
            and_(
                SubjectAssignment.course_id == course_id,
                SubjectAssignment.semester_id == semester_id,
                SubjectAssignment.role_in_course == CourseRoleInCourse.PRIMARY,
                SubjectAssignment.is_active.is_(True),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def find_duplicate(
        course_id: UUID,
        faculty_user_id: UUID,
        semester_id: UUID,
        *,
        db: AsyncSession,
    ) -> SubjectAssignment | None:
        """Return existing active assignment for this faculty+course+semester, if any."""
        stmt = select(SubjectAssignment).where(
            and_(
                SubjectAssignment.course_id == course_id,
                SubjectAssignment.faculty_user_id == faculty_user_id,
                SubjectAssignment.semester_id == semester_id,
                SubjectAssignment.is_active.is_(True),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_for_faculty_course(
        course_id: UUID,
        faculty_user_id: UUID,
        *,
        db: AsyncSession,
    ) -> SubjectAssignment | None:
        """Used by downstream modules (M02/M03/M05) to gate write access."""
        stmt = select(SubjectAssignment).where(
            and_(
                SubjectAssignment.course_id == course_id,
                SubjectAssignment.faculty_user_id == faculty_user_id,
                SubjectAssignment.is_active.is_(True),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
