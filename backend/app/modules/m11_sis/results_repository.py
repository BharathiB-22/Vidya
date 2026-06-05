"""
SIS Results Management — H60 Repository layer.

All queries are scoped to the tenant DB session provided by the caller.
No cross-tenant queries. No raw SQL except where noted.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.m11_sis.results_models import (
    SisGradingPolicy,
    SisGradingPolicyBand,
    SisGraceMarksLog,
    SisResultDeclaration,
    SisExternalMarks,
    SisSemesterResult,
    SisSubjectResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# Grading Policy
# ─────────────────────────────────────────────────────────────────────────────

class GradingPolicyRepo:

    @staticmethod
    async def create(policy: SisGradingPolicy, db: AsyncSession) -> SisGradingPolicy:
        db.add(policy)
        await db.flush()
        await db.refresh(policy)
        return policy

    @staticmethod
    async def get_by_id(policy_id: UUID, db: AsyncSession) -> Optional[SisGradingPolicy]:
        result = await db.execute(
            select(SisGradingPolicy)
            .options(selectinload(SisGradingPolicy.bands))
            .where(SisGradingPolicy.id == policy_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(db: AsyncSession, active_only: bool = True) -> list[SisGradingPolicy]:
        q = select(SisGradingPolicy).options(selectinload(SisGradingPolicy.bands))
        if active_only:
            q = q.where(SisGradingPolicy.is_active == True)
        q = q.order_by(SisGradingPolicy.is_default.desc(), SisGradingPolicy.name)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def get_default(db: AsyncSession) -> Optional[SisGradingPolicy]:
        result = await db.execute(
            select(SisGradingPolicy)
            .options(selectinload(SisGradingPolicy.bands))
            .where(SisGradingPolicy.is_default == True, SisGradingPolicy.is_active == True)
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def clear_default_flag(db: AsyncSession) -> None:
        await db.execute(
            update(SisGradingPolicy)
            .where(SisGradingPolicy.is_default == True)
            .values(is_default=False)
        )

    @staticmethod
    async def add_band(band: SisGradingPolicyBand, db: AsyncSession) -> SisGradingPolicyBand:
        db.add(band)
        await db.flush()
        await db.refresh(band)
        return band

    @staticmethod
    async def get_band(band_id: UUID, db: AsyncSession) -> Optional[SisGradingPolicyBand]:
        result = await db.execute(
            select(SisGradingPolicyBand).where(SisGradingPolicyBand.id == band_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_band(band: SisGradingPolicyBand, db: AsyncSession) -> None:
        await db.delete(band)
        await db.flush()

    @staticmethod
    async def get_bands_for_policy(
        policy_id: UUID, db: AsyncSession
    ) -> list[SisGradingPolicyBand]:
        result = await db.execute(
            select(SisGradingPolicyBand)
            .where(SisGradingPolicyBand.policy_id == policy_id)
            .order_by(SisGradingPolicyBand.display_order.nulls_last(),
                      SisGradingPolicyBand.min_percentage.desc())
        )
        return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# Result Declaration
# ─────────────────────────────────────────────────────────────────────────────

class ResultDeclarationRepo:

    @staticmethod
    async def create(
        declaration: SisResultDeclaration, db: AsyncSession
    ) -> SisResultDeclaration:
        db.add(declaration)
        await db.flush()
        await db.refresh(declaration)
        return declaration

    @staticmethod
    async def get_by_id(
        declaration_id: UUID, db: AsyncSession
    ) -> Optional[SisResultDeclaration]:
        result = await db.execute(
            select(SisResultDeclaration).where(
                SisResultDeclaration.id == declaration_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_semester(
        semester_id: UUID,
        db: AsyncSession,
        status: Optional[str] = None,
        declaration_type: Optional[str] = None,
    ) -> list[SisResultDeclaration]:
        q = (
            select(SisResultDeclaration)
            .where(SisResultDeclaration.semester_id == semester_id)
        )
        if status:
            q = q.where(SisResultDeclaration.status == status)
        if declaration_type:
            q = q.where(SisResultDeclaration.declaration_type == declaration_type)
        q = q.order_by(SisResultDeclaration.created_at.desc())
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def list_published(
        db: AsyncSession, semester_id: Optional[UUID] = None
    ) -> list[SisResultDeclaration]:
        q = select(SisResultDeclaration).where(
            SisResultDeclaration.status.in_(["PUBLISHED", "LOCKED"])
        )
        if semester_id:
            q = q.where(SisResultDeclaration.semester_id == semester_id)
        q = q.order_by(SisResultDeclaration.published_at.desc())
        result = await db.execute(q)
        return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# External Marks
# ─────────────────────────────────────────────────────────────────────────────

class ExternalMarksRepo:

    @staticmethod
    async def upsert(entry: SisExternalMarks, db: AsyncSession) -> SisExternalMarks:
        db.add(entry)
        await db.flush()
        await db.refresh(entry)
        return entry

    @staticmethod
    async def get_by_id(entry_id: UUID, db: AsyncSession) -> Optional[SisExternalMarks]:
        result = await db.execute(
            select(SisExternalMarks).where(SisExternalMarks.id == entry_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_declaration_student_course(
        declaration_id: UUID,
        student_id: UUID,
        course_id: UUID,
        db: AsyncSession,
    ) -> Optional[SisExternalMarks]:
        result = await db.execute(
            select(SisExternalMarks).where(
                SisExternalMarks.declaration_id == declaration_id,
                SisExternalMarks.student_id == student_id,
                SisExternalMarks.course_id == course_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_declaration(
        declaration_id: UUID,
        db: AsyncSession,
        section_id: Optional[UUID] = None,
    ) -> list[SisExternalMarks]:
        q = select(SisExternalMarks).where(
            SisExternalMarks.declaration_id == declaration_id
        )
        if section_id:
            q = q.where(SisExternalMarks.section_id == section_id)
        q = q.order_by(SisExternalMarks.student_id, SisExternalMarks.course_id)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def count_entered(declaration_id: UUID, db: AsyncSession) -> int:
        result = await db.execute(
            select(func.count()).where(
                SisExternalMarks.declaration_id == declaration_id,
                SisExternalMarks.external_marks_obtained.isnot(None)
                | (SisExternalMarks.is_absent == True),
            )
        )
        return result.scalar_one()

    @staticmethod
    async def count_total(declaration_id: UUID, db: AsyncSession) -> int:
        result = await db.execute(
            select(func.count()).where(
                SisExternalMarks.declaration_id == declaration_id
            )
        )
        return result.scalar_one()


# ─────────────────────────────────────────────────────────────────────────────
# Subject Results
# ─────────────────────────────────────────────────────────────────────────────

class SubjectResultRepo:

    @staticmethod
    async def upsert(row: SisSubjectResult, db: AsyncSession) -> SisSubjectResult:
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return row

    @staticmethod
    async def get_by_id(result_id: UUID, db: AsyncSession) -> Optional[SisSubjectResult]:
        result = await db.execute(
            select(SisSubjectResult).where(SisSubjectResult.id == result_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_declaration_student_course(
        declaration_id: UUID,
        student_id: UUID,
        course_id: UUID,
        db: AsyncSession,
    ) -> Optional[SisSubjectResult]:
        result = await db.execute(
            select(SisSubjectResult).where(
                SisSubjectResult.declaration_id == declaration_id,
                SisSubjectResult.student_id == student_id,
                SisSubjectResult.course_id == course_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_declaration(
        declaration_id: UUID,
        db: AsyncSession,
        student_id: Optional[UUID] = None,
        section_id: Optional[UUID] = None,
    ) -> list[SisSubjectResult]:
        q = select(SisSubjectResult).where(
            SisSubjectResult.declaration_id == declaration_id
        )
        if student_id:
            q = q.where(SisSubjectResult.student_id == student_id)
        if section_id:
            q = q.where(SisSubjectResult.section_id == section_id)
        q = q.order_by(SisSubjectResult.student_id, SisSubjectResult.course_id)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def list_by_student(
        student_id: UUID,
        db: AsyncSession,
        published_only: bool = True,
    ) -> list[SisSubjectResult]:
        q = (
            select(SisSubjectResult)
            .join(
                SisResultDeclaration,
                SisSubjectResult.declaration_id == SisResultDeclaration.id,
            )
            .where(SisSubjectResult.student_id == student_id)
        )
        if published_only:
            q = q.where(SisResultDeclaration.status.in_(["PUBLISHED", "LOCKED"]))
        q = q.order_by(SisSubjectResult.semester_id, SisSubjectResult.course_id)
        result = await db.execute(q)
        return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# Semester Results
# ─────────────────────────────────────────────────────────────────────────────

class SemesterResultRepo:

    @staticmethod
    async def upsert(row: SisSemesterResult, db: AsyncSession) -> SisSemesterResult:
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return row

    @staticmethod
    async def get_by_declaration_student(
        declaration_id: UUID, student_id: UUID, db: AsyncSession
    ) -> Optional[SisSemesterResult]:
        result = await db.execute(
            select(SisSemesterResult).where(
                SisSemesterResult.declaration_id == declaration_id,
                SisSemesterResult.student_id == student_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_declaration(
        declaration_id: UUID, db: AsyncSession
    ) -> list[SisSemesterResult]:
        result = await db.execute(
            select(SisSemesterResult)
            .where(SisSemesterResult.declaration_id == declaration_id)
            .order_by(SisSemesterResult.sgpa.desc().nulls_last())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_by_student(
        student_id: UUID,
        db: AsyncSession,
        published_only: bool = True,
    ) -> list[SisSemesterResult]:
        q = (
            select(SisSemesterResult)
            .join(
                SisResultDeclaration,
                SisSemesterResult.declaration_id == SisResultDeclaration.id,
            )
            .where(SisSemesterResult.student_id == student_id)
        )
        if published_only:
            q = q.where(SisResultDeclaration.status.in_(["PUBLISHED", "LOCKED"]))
        q = q.order_by(SisSemesterResult.semester_id)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def list_by_section(
        declaration_id: UUID,
        section_id: UUID,
        db: AsyncSession,
    ) -> list[SisSemesterResult]:
        """Semester results for all students in a section (for rank computation)."""
        q = (
            select(SisSemesterResult)
            .join(
                SisSubjectResult,
                (SisSubjectResult.declaration_id == SisSemesterResult.declaration_id)
                & (SisSubjectResult.student_id == SisSemesterResult.student_id)
                & (SisSubjectResult.section_id == section_id),
            )
            .where(SisSemesterResult.declaration_id == declaration_id)
            .distinct()
        )
        result = await db.execute(q)
        return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# Grace Marks Log
# ─────────────────────────────────────────────────────────────────────────────

class GraceMarksLogRepo:

    @staticmethod
    async def create(log: SisGraceMarksLog, db: AsyncSession) -> SisGraceMarksLog:
        db.add(log)
        await db.flush()
        await db.refresh(log)
        return log

    @staticmethod
    async def get_by_id(log_id: UUID, db: AsyncSession) -> Optional[SisGraceMarksLog]:
        result = await db.execute(
            select(SisGraceMarksLog).where(SisGraceMarksLog.id == log_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_declaration(
        declaration_id: UUID, db: AsyncSession
    ) -> list[SisGraceMarksLog]:
        result = await db.execute(
            select(SisGraceMarksLog)
            .where(SisGraceMarksLog.declaration_id == declaration_id)
            .order_by(SisGraceMarksLog.authorized_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_active_for_subject_result(
        subject_result_id: UUID, db: AsyncSession
    ) -> Optional[SisGraceMarksLog]:
        result = await db.execute(
            select(SisGraceMarksLog).where(
                SisGraceMarksLog.subject_result_id == subject_result_id,
                SisGraceMarksLog.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()
