"""
SIS Directory Service — H50.

Business logic for student and faculty directory pages.
All profile mutations are audit-logged.
"""
from __future__ import annotations

import math
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.models import TenantRole, User
from app.modules.m11_sis.directory_repository import (
    FacultyDirectoryRepository,
    StudentDirectoryRepository,
)
from app.modules.m11_sis.directory_schemas import (
    AssignmentMini,
    BatchMini,
    CourseMini,
    DeptMini,
    DirectoryPage,
    FacultyDetailOut,
    FacultyDirectoryItem,
    FacultyProfileUpsert,
    ProgramMini,
    SectionMini,
    StudentDetailOut,
    StudentDirectoryItem,
    StudentProfileUpsert,
)
from app.modules.m11_sis.models import SisFacultyProfile, SisStudentProfile


class DirectoryServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Helpers — row-to-schema converters
# ---------------------------------------------------------------------------

def _build_student_item(row) -> StudentDirectoryItem:
    user, profile, program, dept, batch, section = row
    return StudentDirectoryItem(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        identifier=user.identifier,
        usn=profile.usn if profile else None,
        admission_year=profile.admission_year if profile else None,
        program=ProgramMini(id=program.id, name=program.name, code=program.code, degree_type=program.degree_type) if program else None,
        department=DeptMini(id=dept.id, name=dept.name, code=dept.code) if dept else None,
        batch=BatchMini(id=batch.id, name=batch.name, start_year=batch.start_year, end_year=batch.end_year) if batch else None,
        current_section=SectionMini(id=section.id, name=section.name) if section else None,
        is_active=user.is_active,
    )


def _build_faculty_item(row) -> FacultyDirectoryItem:
    user, profile, dept = row
    return FacultyDirectoryItem(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        employee_id=profile.employee_id if profile else None,
        designation=profile.designation if profile else None,
        specialization=profile.specialization if profile else None,
        primary_department=DeptMini(id=dept.id, name=dept.name, code=dept.code) if dept else None,
        photo_url=profile.photo_url if profile else None,
        is_active=user.is_active,
    )


def _semester_label(sem) -> str:
    if sem is None:
        return "Unknown"
    return f"Sem {sem.number}" + (f" – {sem.label}" if sem.label else "")


def _make_page(items, total, page, page_size):
    return DirectoryPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, math.ceil(total / page_size)),
    )


# ---------------------------------------------------------------------------
# Student directory
# ---------------------------------------------------------------------------

class StudentDirectoryService:

    @staticmethod
    async def list_directory(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        program_id: UUID | None = None,
        batch_id: UUID | None = None,
        section_id: UUID | None = None,
        is_active: bool | None = None,
    ) -> DirectoryPage[StudentDirectoryItem]:
        rows, total = await StudentDirectoryRepository.list_paginated(
            db,
            page=page,
            page_size=page_size,
            search=search,
            program_id=program_id,
            batch_id=batch_id,
            section_id=section_id,
            is_active=is_active,
        )
        return _make_page([_build_student_item(r) for r in rows], total, page, page_size)

    @staticmethod
    async def get_detail(user_id: UUID, db: AsyncSession) -> StudentDetailOut:
        row = await StudentDirectoryRepository.get_by_user_id(user_id, db)
        if row is None:
            raise DirectoryServiceError("NOT_FOUND", "Student not found.", 404)
        user, profile, program, dept, batch, section = row
        if user.role != TenantRole.STUDENT:
            raise DirectoryServiceError("NOT_FOUND", "Student not found.", 404)
        return StudentDetailOut(
            user_id=user.id,
            full_name=user.full_name,
            email=user.email,
            identifier=user.identifier,
            usn=profile.usn if profile else None,
            admission_year=profile.admission_year if profile else None,
            date_of_birth=profile.date_of_birth if profile else None,
            phone=profile.phone if profile else None,
            address_line1=profile.address_line1 if profile else None,
            address_city=profile.address_city if profile else None,
            address_state=profile.address_state if profile else None,
            emergency_contact_name=profile.emergency_contact_name if profile else None,
            emergency_contact_phone=profile.emergency_contact_phone if profile else None,
            photo_url=profile.photo_url if profile else None,
            notes=profile.notes if profile else None,
            program=ProgramMini(id=program.id, name=program.name, code=program.code, degree_type=program.degree_type) if program else None,
            department=DeptMini(id=dept.id, name=dept.name, code=dept.code) if dept else None,
            batch=BatchMini(id=batch.id, name=batch.name, start_year=batch.start_year, end_year=batch.end_year) if batch else None,
            current_section=SectionMini(id=section.id, name=section.name) if section else None,
            is_active=user.is_active,
            profile_created_at=profile.created_at if profile else None,
            profile_updated_at=profile.updated_at if profile else None,
        )

    @staticmethod
    async def upsert_profile(
        user_id: UUID,
        body: StudentProfileUpsert,
        actor_user_id: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> StudentDetailOut:
        result = await db.execute(select(User).where(User.id == user_id))
        target = result.scalar_one_or_none()
        if target is None or target.role != TenantRole.STUDENT:
            raise DirectoryServiceError("NOT_FOUND", "Student not found.", 404)

        updates = body.model_dump(exclude_none=True)

        # USN uniqueness check
        if "usn" in updates:
            dup = await db.execute(
                select(SisStudentProfile).where(
                    SisStudentProfile.usn == updates["usn"],
                    SisStudentProfile.user_id != user_id,
                )
            )
            if dup.scalar_one_or_none():
                raise DirectoryServiceError(
                    "DUPLICATE_USN",
                    f"USN '{updates['usn']}' is already assigned to another student.",
                )

        await StudentDirectoryRepository.upsert_profile(user_id, updates, db)
        await db.commit()
        await AuditService.log(
            AuditEventType.STUDENT_PROFILE_UPDATED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="sis_student_profile",
            target_id=str(user_id),
            metadata={"fields_updated": list(updates.keys())},
        )
        return await StudentDirectoryService.get_detail(user_id, db)


# ---------------------------------------------------------------------------
# Faculty directory
# ---------------------------------------------------------------------------

class FacultyDirectoryService:

    @staticmethod
    async def list_directory(
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        department_id: UUID | None = None,
        is_active: bool | None = None,
    ) -> DirectoryPage[FacultyDirectoryItem]:
        rows, total = await FacultyDirectoryRepository.list_paginated(
            db,
            page=page,
            page_size=page_size,
            search=search,
            department_id=department_id,
            is_active=is_active,
        )
        return _make_page([_build_faculty_item(r) for r in rows], total, page, page_size)

    @staticmethod
    async def get_detail(user_id: UUID, db: AsyncSession) -> FacultyDetailOut:
        row = await FacultyDirectoryRepository.get_by_user_id(user_id, db)
        if row is None:
            raise DirectoryServiceError("NOT_FOUND", "Faculty member not found.", 404)
        user, profile, dept = row
        if user.role != TenantRole.FACULTY:
            raise DirectoryServiceError("NOT_FOUND", "Faculty member not found.", 404)

        assignment_rows = await FacultyDirectoryRepository.get_active_assignments(user_id, db)
        assignments = []
        for sa_row, course, sem in assignment_rows:
            if course is not None:
                course_mini = CourseMini(id=course.id, name=course.name, code=course.code)
            else:
                course_mini = CourseMini(id=sa_row.course_id, name="Unknown course", code="—")
            assignments.append(AssignmentMini(
                course=course_mini,
                semester_label=_semester_label(sem),
                role=sa_row.role_in_course,
            ))

        return FacultyDetailOut(
            user_id=user.id,
            full_name=user.full_name,
            email=user.email,
            identifier=user.identifier,
            employee_id=profile.employee_id if profile else None,
            designation=profile.designation if profile else None,
            qualifications=profile.qualifications if profile else None,
            bio=profile.bio if profile else None,
            office_location=profile.office_location if profile else None,
            phone=profile.phone if profile else None,
            joining_date=profile.joining_date if profile else None,
            specialization=profile.specialization if profile else None,
            primary_department=DeptMini(id=dept.id, name=dept.name, code=dept.code) if dept else None,
            photo_url=profile.photo_url if profile else None,
            active_assignments=assignments,
            is_active=user.is_active,
            profile_created_at=profile.created_at if profile else None,
            profile_updated_at=profile.updated_at if profile else None,
        )

    @staticmethod
    async def upsert_profile(
        user_id: UUID,
        body: FacultyProfileUpsert,
        actor_user_id: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> FacultyDetailOut:
        result = await db.execute(select(User).where(User.id == user_id))
        target = result.scalar_one_or_none()
        if target is None or target.role != TenantRole.FACULTY:
            raise DirectoryServiceError("NOT_FOUND", "Faculty member not found.", 404)

        # employee_id uniqueness check
        dup = await db.execute(
            select(SisFacultyProfile).where(
                SisFacultyProfile.employee_id == body.employee_id,
                SisFacultyProfile.user_id != user_id,
            )
        )
        if dup.scalar_one_or_none():
            raise DirectoryServiceError(
                "DUPLICATE_EMPLOYEE_ID",
                f"Employee ID '{body.employee_id}' is already assigned.",
            )

        updates = body.model_dump(exclude_none=True)
        await FacultyDirectoryRepository.upsert_profile(user_id, updates, db)
        await db.commit()
        await AuditService.log(
            AuditEventType.FACULTY_PROFILE_UPDATED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="sis_faculty_profile",
            target_id=str(user_id),
            metadata={"fields_updated": list(updates.keys())},
        )
        return await FacultyDirectoryService.get_detail(user_id, db)

    @staticmethod
    async def list_by_department(
        department_id: UUID, db: AsyncSession
    ) -> DirectoryPage[FacultyDirectoryItem]:
        rows, total = await FacultyDirectoryRepository.list_by_department(department_id, db)
        return _make_page([_build_faculty_item(r) for r in rows], total, 1, total or 1)
