"""
SIS Enrollment — M11-002 Repository.

All queries run in the tenant schema (search_path injected by the engine
begin event).  acad_enrollments.student_id is a plain UUID with no FK —
joins against users are explicit.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.models import TenantRole, User
from app.modules.m11_sis.models import SisSchool
from app.modules.m_academics.models import (
    AcadBatch, AcadDepartment, AcadEnrollment,
    AcadProgram, AcadSection, AcadSemester,
)
from app.modules.m11_sis.enrollment_schemas import (
    BatchSummary, DashboardCountsOut, DeptSummary,
    EnrollmentOut, EnrollmentSummary, ProgramSummary,
    RosterStudentOut, SectionSummary, SemesterSummary,
    StudentProfileOut, StudentSummaryOut,
)


class EnrollmentRepository:

    # ------------------------------------------------------------------
    # Roster
    # ------------------------------------------------------------------

    @staticmethod
    async def get_roster(
        section_id: UUID,
        db: AsyncSession,
        include_inactive: bool = False,
    ) -> list[RosterStudentOut]:
        stmt = (
            select(
                AcadEnrollment.id.label("enrollment_id"),
                AcadEnrollment.student_id,
                AcadEnrollment.enrolled_at,
                AcadEnrollment.is_active,
                User.full_name,
                User.email,
                User.identifier,
            )
            .join(User, User.id == AcadEnrollment.student_id)
            .where(AcadEnrollment.section_id == section_id)
        )
        if not include_inactive:
            stmt = stmt.where(AcadEnrollment.is_active.is_(True))
        stmt = stmt.order_by(User.full_name)
        result = await db.execute(stmt)
        return [
            RosterStudentOut(
                enrollment_id=row.enrollment_id,
                student_id=row.student_id,
                full_name=row.full_name,
                email=row.email,
                identifier=row.identifier,
                enrolled_at=row.enrolled_at,
                is_active=row.is_active,
            )
            for row in result.all()
        ]

    # ------------------------------------------------------------------
    # Single enrollment lookups
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(enrollment_id: UUID, db: AsyncSession) -> AcadEnrollment | None:
        result = await db.execute(
            select(AcadEnrollment).where(AcadEnrollment.id == enrollment_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_student(student_id: UUID, db: AsyncSession) -> AcadEnrollment | None:
        """Return the enrollment record for this student (active or inactive)."""
        result = await db.execute(
            select(AcadEnrollment).where(AcadEnrollment.student_id == student_id)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        student_id: UUID,
        section_id: UUID,
        db: AsyncSession,
    ) -> AcadEnrollment:
        enrollment = AcadEnrollment(
            student_id=student_id,
            section_id=section_id,
            is_active=True,
        )
        db.add(enrollment)
        await db.flush()
        await db.refresh(enrollment)
        return enrollment

    @staticmethod
    async def reenroll(
        enrollment: AcadEnrollment,
        section_id: UUID,
        db: AsyncSession,
    ) -> AcadEnrollment:
        """Update an inactive enrollment record to re-enroll the student."""
        enrollment.section_id = section_id
        enrollment.is_active = True
        enrollment.enrolled_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(enrollment)
        return enrollment

    @staticmethod
    async def unenroll(
        enrollment: AcadEnrollment,
        db: AsyncSession,
    ) -> AcadEnrollment:
        enrollment.is_active = False
        await db.flush()
        await db.refresh(enrollment)
        return enrollment

    @staticmethod
    async def move(
        enrollment: AcadEnrollment,
        target_section_id: UUID,
        db: AsyncSession,
    ) -> AcadEnrollment:
        enrollment.section_id = target_section_id
        await db.flush()
        await db.refresh(enrollment)
        return enrollment

    # ------------------------------------------------------------------
    # Student list (enroll-picker)
    # ------------------------------------------------------------------

    @staticmethod
    async def list_students(
        db: AsyncSession,
        search: Optional[str] = None,
        limit: int = 100,
    ) -> list[StudentSummaryOut]:
        stmt = (
            select(
                User.id,
                User.full_name,
                User.email,
                User.identifier,
                AcadEnrollment.id.label("enrollment_id"),
            )
            .outerjoin(
                AcadEnrollment,
                (AcadEnrollment.student_id == User.id)
                & AcadEnrollment.is_active.is_(True),
            )
            .where(User.role == TenantRole.STUDENT)
            .where(User.is_active.is_(True))
        )
        if search:
            q = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(User.full_name).like(q),
                    func.lower(User.email).like(q),
                )
            )
        stmt = stmt.order_by(User.full_name).limit(limit)
        result = await db.execute(stmt)
        return [
            StudentSummaryOut(
                id=row.id,
                full_name=row.full_name,
                email=row.email,
                identifier=row.identifier,
                is_enrolled=row.enrollment_id is not None,
            )
            for row in result.all()
        ]

    # ------------------------------------------------------------------
    # Student academic profile (chain of individual lookups)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_student_profile(
        student_id: UUID,
        db: AsyncSession,
    ) -> StudentProfileOut | None:
        # 1. User
        user = (await db.execute(select(User).where(User.id == student_id))).scalar_one_or_none()
        if user is None:
            return None

        # 2. Program + Department + Batch (via users.acad_program_id)
        program_out: Optional[ProgramSummary] = None
        dept_out: Optional[DeptSummary] = None
        batch_out: Optional[BatchSummary] = None

        if user.acad_program_id:
            prog = (
                await db.execute(select(AcadProgram).where(AcadProgram.id == user.acad_program_id))
            ).scalar_one_or_none()
            if prog:
                program_out = ProgramSummary(
                    id=prog.id, name=prog.name,
                    code=prog.code, degree_type=prog.degree_type,
                )
                dept = (
                    await db.execute(select(AcadDepartment).where(AcadDepartment.id == prog.department_id))
                ).scalar_one_or_none()
                if dept:
                    dept_out = DeptSummary(id=dept.id, name=dept.name, code=dept.code)

                # Most recent active batch for this program
                batch = (
                    await db.execute(
                        select(AcadBatch)
                        .where(AcadBatch.program_id == prog.id)
                        .where(AcadBatch.is_active.is_(True))
                        .order_by(AcadBatch.start_year.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if batch:
                    batch_out = BatchSummary(
                        id=batch.id, name=batch.name,
                        start_year=batch.start_year, end_year=batch.end_year,
                    )

        # 3. Current active enrollment → section → semester
        enrollment_out: Optional[EnrollmentSummary] = None
        enrollment = (
            await db.execute(
                select(AcadEnrollment)
                .where(AcadEnrollment.student_id == student_id)
                .where(AcadEnrollment.is_active.is_(True))
            )
        ).scalar_one_or_none()
        if enrollment:
            section = (
                await db.execute(select(AcadSection).where(AcadSection.id == enrollment.section_id))
            ).scalar_one_or_none()
            if section:
                semester = (
                    await db.execute(select(AcadSemester).where(AcadSemester.id == section.semester_id))
                ).scalar_one_or_none()
                if semester:
                    enrollment_out = EnrollmentSummary(
                        enrollment_id=enrollment.id,
                        section=SectionSummary(id=section.id, name=section.name),
                        semester=SemesterSummary(
                            id=semester.id,
                            number=semester.number,
                            label=semester.label,
                        ),
                    )

        return StudentProfileOut(
            student_id=user.id,
            full_name=user.full_name,
            email=user.email,
            identifier=user.identifier,
            program=program_out,
            department=dept_out,
            batch=batch_out,
            enrollment=enrollment_out,
        )

    # ------------------------------------------------------------------
    # Dashboard counts
    # ------------------------------------------------------------------

    @staticmethod
    async def get_dashboard_counts(db: AsyncSession) -> DashboardCountsOut:
        async def _count(model) -> int:
            stmt = select(func.count()).select_from(model)
            if hasattr(model, "is_active"):
                stmt = stmt.where(model.is_active.is_(True))
            return (await db.execute(stmt)).scalar() or 0

        return DashboardCountsOut(
            schools=await _count(SisSchool),
            departments=await _count(AcadDepartment),
            programs=await _count(AcadProgram),
            active_batches=await _count(AcadBatch),
            semesters=await _count(AcadSemester),
            sections=await _count(AcadSection),
            enrolled_students=await _count(AcadEnrollment),
        )
