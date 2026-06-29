"""
SIS Directory Service — H50.

Business logic for student and faculty directory pages.
All profile mutations are audit-logged.
"""
from __future__ import annotations

import logging
import math
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("vidya.sis.directory")

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
    FacultySelfServiceUpdate,
    ProgramMini,
    SectionMini,
    StudentDetailOut,
    StudentDirectoryItem,
    StudentProfileUpsert,
    StudentSelfServiceUpdate,
)
from app.modules.m11_sis.models import SisFacultyProfile, SisStudentProfile


class DirectoryServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def _notify_safe(
    *,
    notification_type,
    recipient_user_id: UUID,
    recipient_email: str | None,
    title: str,
    body: str,
    entity_type: str,
    entity_id: str,
    db,
) -> None:
    """Fire-and-forget notification. Never raises — a failure is logged only."""
    try:
        from app.core.notifications.service import NotificationService
        await NotificationService.send(
            notification_type,
            recipient_user_id=recipient_user_id,
            recipient_email=recipient_email,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
            db=db,
        )
    except Exception:
        logger.warning(
            "notification_failed type=%s recipient=%s",
            notification_type,
            recipient_user_id,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Helpers — row-to-schema converters
# ---------------------------------------------------------------------------

def _build_student_item(row) -> StudentDirectoryItem:
    user, profile, program, dept, batch, section = row
    return StudentDirectoryItem(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        institution_email=user.institution_email,
        identifier=user.identifier,
        usn=profile.usn if profile else None,
        admission_year=profile.admission_year if profile else None,
        program=ProgramMini(id=program.id, name=program.name, code=program.code, degree_type=program.degree_type) if program else None,
        department=DeptMini(id=dept.id, name=dept.name, code=dept.code) if dept else None,
        batch=BatchMini(id=batch.id, name=batch.name, start_year=batch.start_year, end_year=batch.end_year) if batch else None,
        current_section=SectionMini(id=section.id, name=section.name) if section else None,
        is_active=user.is_active,
    )


_FACULTY_LIKE_ROLES = frozenset({TenantRole.FACULTY, TenantRole.DEAN})


def _build_faculty_item(row, responsibilities: list[str] | None = None) -> FacultyDirectoryItem:
    user, profile, dept = row
    # Surface DEAN role as a chip so deans display their role badge in the
    # Faculty Directory card alongside GUIDE/EVALUATOR grants.
    resps: list[str] = list(responsibilities or [])
    if user.role == TenantRole.DEAN and "DEAN" not in resps:
        resps = ["DEAN"] + resps
    return FacultyDirectoryItem(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        employee_id=profile.employee_id if profile else None,
        faculty_code=profile.faculty_code if profile else None,
        designation=profile.designation if profile else None,
        specialization=profile.specialization if profile else None,
        primary_department=DeptMini(id=dept.id, name=dept.name, code=dept.code) if dept else None,
        photo_url=profile.photo_url if profile else None,
        responsibilities=resps,
        is_active=user.is_active,
    )


async def _active_grants_for(user_id: UUID, db: AsyncSession) -> list[str]:
    """Active responsibility role_codes held by a single faculty user (sorted)."""
    rows = await db.execute(
        text(
            "SELECT role_code FROM faculty_role_grants "
            "WHERE faculty_user_id = :u AND is_active = true"
        ),
        {"u": str(user_id)},
    )
    return sorted({r[0] for r in rows.fetchall()})


async def _active_grants_for_many(
    user_ids: list[UUID], db: AsyncSession
) -> dict[str, list[str]]:
    """Active grants keyed by user-id (string) for a batch of faculty — one query."""
    if not user_ids:
        return {}
    rows = await db.execute(
        text(
            "SELECT faculty_user_id::text AS uid, role_code FROM faculty_role_grants "
            "WHERE faculty_user_id = ANY(:ids) AND is_active = true"
        ),
        {"ids": [str(u) for u in user_ids]},
    )
    out: dict[str, list[str]] = {}
    for uid, role_code in rows.fetchall():
        out.setdefault(uid, []).append(role_code)
    return {uid: sorted(set(v)) for uid, v in out.items()}


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
        department_id: UUID | None = None,
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
            department_id=department_id,
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
            institution_email=user.institution_email,
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

        from app.core.notifications.models import NotificationType
        if "usn" in updates:
            await _notify_safe(
                notification_type=NotificationType.USN_ASSIGNED,
                recipient_user_id=target.id,
                recipient_email=target.email,
                title="USN Assigned",
                body=f"Your University Serial Number (USN) has been set to \"{updates['usn']}\".",
                entity_type="sis_student_profile",
                entity_id=str(user_id),
                db=db,
            )
        if "admission_year" in updates:
            await _notify_safe(
                notification_type=NotificationType.ADMISSION_YEAR_ASSIGNED,
                recipient_user_id=target.id,
                recipient_email=target.email,
                title="Admission Year Assigned",
                body=f"Your admission year has been set to {updates['admission_year']}.",
                entity_type="sis_student_profile",
                entity_id=str(user_id),
                db=db,
            )

        return await StudentDirectoryService.get_detail(user_id, db)

    @staticmethod
    async def upsert_own_profile(
        current_user_id: UUID,
        body: StudentSelfServiceUpdate,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> StudentDetailOut:
        """Self-service update: student edits only their own contact fields."""
        updates = body.model_dump(exclude_none=True)
        await StudentDirectoryRepository.upsert_profile(current_user_id, updates, db)
        await db.commit()
        await AuditService.log(
            AuditEventType.STUDENT_PROFILE_UPDATED,
            actor_user_id=current_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="sis_student_profile",
            target_id=str(current_user_id),
            metadata={"fields_updated": list(updates.keys()), "self_service": True},
        )
        return await StudentDirectoryService.get_detail(current_user_id, db)


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
        grants = await _active_grants_for_many([r[0].id for r in rows], db)
        items = [_build_faculty_item(r, grants.get(str(r[0].id), [])) for r in rows]
        return _make_page(items, total, page, page_size)

    @staticmethod
    async def get_detail(user_id: UUID, db: AsyncSession) -> FacultyDetailOut:
        row = await FacultyDirectoryRepository.get_by_user_id(user_id, db)
        if row is None:
            raise DirectoryServiceError("NOT_FOUND", "Faculty member not found.", 404)
        user, profile, dept = row
        if user.role not in _FACULTY_LIKE_ROLES:
            raise DirectoryServiceError("NOT_FOUND", "Faculty member not found.", 404)

        assignment_rows = await FacultyDirectoryRepository.get_active_assignments(user_id, db)
        assignments = []
        for sa_row, course, sem, section in assignment_rows:
            if course is not None:
                course_mini = CourseMini(id=course.id, name=course.title, code=course.code)
            else:
                course_mini = CourseMini(id=sa_row.course_id, name="Unknown course", code="—")
            assignments.append(AssignmentMini(
                course=course_mini,
                semester_label=_semester_label(sem),
                section=SectionMini(id=section.id, name=section.name) if section else None,
                role=sa_row.role_in_course,
            ))

        responsibilities = await _active_grants_for(user_id, db)
        if user.role == TenantRole.DEAN and "DEAN" not in responsibilities:
            responsibilities = ["DEAN"] + responsibilities

        teaching_program_rows = await FacultyDirectoryRepository.get_teaching_programs(user_id, db)
        teaching_programs = [
            ProgramMini(id=r["program_id"], name=r["program_name"], code=r["program_code"], degree_type=r["degree_type"])
            for r in teaching_program_rows
        ]

        governing_programs: list[ProgramMini] = []
        if user.role == TenantRole.DEAN:
            governing_rows = await FacultyDirectoryRepository.get_governing_programs(user_id, db)
            governing_programs = [
                ProgramMini(id=prog.id, name=prog.name, code=prog.code, degree_type=prog.degree_type)
                for _, prog in governing_rows
            ]

        return FacultyDetailOut(
            user_id=user.id,
            full_name=user.full_name,
            email=user.email,
            identifier=user.identifier,
            employee_id=profile.employee_id if profile else None,
            faculty_code=profile.faculty_code if profile else None,
            institution_email=profile.institution_email if profile else None,
            responsibilities=responsibilities,
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
            teaching_programs=teaching_programs,
            governing_programs=governing_programs,
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
        if target is None or target.role not in _FACULTY_LIKE_ROLES:
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
    async def upsert_own_profile(
        current_user_id: UUID,
        body: FacultySelfServiceUpdate,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> FacultyDetailOut:
        """Self-service update: faculty edits only their own contact/bio fields."""
        updates = body.model_dump(exclude_none=True)
        await FacultyDirectoryRepository.upsert_profile(current_user_id, updates, db)
        await db.commit()
        await AuditService.log(
            AuditEventType.FACULTY_PROFILE_UPDATED,
            actor_user_id=current_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="sis_faculty_profile",
            target_id=str(current_user_id),
            metadata={"fields_updated": list(updates.keys()), "self_service": True},
        )
        return await FacultyDirectoryService.get_detail(current_user_id, db)

    @staticmethod
    async def list_by_department(
        department_id: UUID, db: AsyncSession
    ) -> DirectoryPage[FacultyDirectoryItem]:
        rows, total = await FacultyDirectoryRepository.list_by_department(department_id, db)
        return _make_page([_build_faculty_item(r) for r in rows], total, 1, total or 1)
