"""
SIS Enrollment — M11-002 Service.

Business rules:
  - One enrollment record per student (UNIQUE on student_id in acad_enrollments).
  - Enrolling an already-enrolled student is rejected (409 ALREADY_ENROLLED).
  - A student with an inactive enrollment record is re-enrolled by updating the
    existing row (avoids violating the unique constraint).
  - Unenroll sets is_active=False; move changes section_id on the active record.
  - Audit events: ENROLLMENT_CREATED, ENROLLMENT_UNENROLLED, ENROLLMENT_MOVED.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.models import TenantRole, User
from app.modules.m_academics.models import AcadSection
from app.modules.m11_sis.enrollment_repository import EnrollmentRepository
from app.modules.m11_sis.enrollment_schemas import (
    DashboardCountsOut,
    EnrollStudentIn,
    EnrollmentOut,
    MoveStudentIn,
    RosterStudentOut,
    StudentProfileOut,
    StudentSummaryOut,
)

logger = logging.getLogger("vidya.sis.enrollment")


class EnrollmentServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _notify_safe(
    *,
    notification_type,
    recipient_user_id: UUID,
    recipient_email: str | None,
    title: str,
    body: str,
    entity_type: str,
    entity_id: str,
    db: AsyncSession,
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
            "notification_failed type=%s recipient=%s entity_id=%s",
            notification_type,
            recipient_user_id,
            entity_id,
            exc_info=True,
        )


class EnrollmentService:

    @staticmethod
    async def get_roster(
        section_id: UUID,
        db: AsyncSession,
        include_inactive: bool = False,
    ) -> list[RosterStudentOut]:
        section = (
            await db.execute(select(AcadSection).where(AcadSection.id == section_id))
        ).scalar_one_or_none()
        if section is None:
            raise EnrollmentServiceError("SECTION_NOT_FOUND", "Section not found.", 404)
        return await EnrollmentRepository.get_roster(section_id, db, include_inactive)

    @staticmethod
    async def enroll_student(
        body: EnrollStudentIn,
        db: AsyncSession,
        actor_user_id: UUID | None = None,
        actor_role: str | None = None,
        tenant_id: UUID | None = None,
        schema_name: str | None = None,
    ) -> EnrollmentOut:
        # Validate student
        user = (
            await db.execute(select(User).where(User.id == body.student_id))
        ).scalar_one_or_none()
        if user is None:
            raise EnrollmentServiceError("STUDENT_NOT_FOUND", "Student not found.", 404)
        if user.role != TenantRole.STUDENT:
            raise EnrollmentServiceError(
                "NOT_A_STUDENT", "User does not have the STUDENT role.", 400
            )

        # Validate section
        section = (
            await db.execute(select(AcadSection).where(AcadSection.id == body.section_id))
        ).scalar_one_or_none()
        if section is None:
            raise EnrollmentServiceError("SECTION_NOT_FOUND", "Section not found.", 404)
        if not section.is_active:
            raise EnrollmentServiceError("SECTION_INACTIVE", "Section is not active.", 409)

        # Capacity gate
        from app.modules.m11_sis.capacity_service import CapacityError, CapacityService
        try:
            await CapacityService.check_capacity(body.section_id, db=db)
        except CapacityError as cap_err:
            raise EnrollmentServiceError(cap_err.code, cap_err.message, cap_err.status_code)

        # Handle UNIQUE constraint: one enrollment record per student
        existing = await EnrollmentRepository.get_by_student(body.student_id, db)
        if existing:
            if existing.is_active:
                raise EnrollmentServiceError(
                    "ALREADY_ENROLLED",
                    "Student is already enrolled in a section. "
                    "Unenroll first, or use move to change section.",
                    409,
                )
            # Re-enroll: update existing inactive record
            enrollment = await EnrollmentRepository.reenroll(existing, body.section_id, db)
        else:
            enrollment = await EnrollmentRepository.create(body.student_id, body.section_id, db)

        await db.commit()

        await AuditService.log(
            AuditEventType.ENROLLMENT_CREATED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="acad_enrollment",
            target_id=str(enrollment.id),
            metadata={
                "student_id": str(body.student_id),
                "section_id": str(body.section_id),
            },
        )

        from app.core.notifications.models import NotificationType
        await _notify_safe(
            notification_type=NotificationType.ENROLLMENT_CREATED,
            recipient_user_id=user.id,
            recipient_email=user.email,
            title="Enrollment Confirmed",
            body=f"You have been enrolled in section \"{section.name}\".",
            entity_type="acad_enrollment",
            entity_id=str(enrollment.id),
            db=db,
        )

        return EnrollmentOut.model_validate(enrollment)

    @staticmethod
    async def unenroll(
        enrollment_id: UUID,
        db: AsyncSession,
        actor_user_id: UUID | None = None,
        actor_role: str | None = None,
        tenant_id: UUID | None = None,
        schema_name: str | None = None,
    ) -> None:
        enrollment = await EnrollmentRepository.get_by_id(enrollment_id, db)
        if enrollment is None:
            raise EnrollmentServiceError("ENROLLMENT_NOT_FOUND", "Enrollment not found.", 404)
        if not enrollment.is_active:
            raise EnrollmentServiceError(
                "ALREADY_UNENROLLED", "Student is already unenrolled.", 409
            )

        student_id = enrollment.student_id

        # Fetch student email before unenroll so we can notify after commit
        student = (
            await db.execute(select(User).where(User.id == student_id))
        ).scalar_one_or_none()

        await EnrollmentRepository.unenroll(enrollment, db)
        await db.commit()

        await AuditService.log(
            AuditEventType.ENROLLMENT_UNENROLLED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="acad_enrollment",
            target_id=str(enrollment_id),
            metadata={"student_id": str(student_id)},
        )

        if student is not None:
            from app.core.notifications.models import NotificationType
            await _notify_safe(
                notification_type=NotificationType.ENROLLMENT_UNENROLLED,
                recipient_user_id=student.id,
                recipient_email=student.email,
                title="Enrollment Removed",
                body="Your section enrollment has been removed.",
                entity_type="acad_enrollment",
                entity_id=str(enrollment_id),
                db=db,
            )

    @staticmethod
    async def move_student(
        enrollment_id: UUID,
        body: MoveStudentIn,
        db: AsyncSession,
        actor_user_id: UUID | None = None,
        actor_role: str | None = None,
        tenant_id: UUID | None = None,
        schema_name: str | None = None,
    ) -> EnrollmentOut:
        enrollment = await EnrollmentRepository.get_by_id(enrollment_id, db)
        if enrollment is None:
            raise EnrollmentServiceError("ENROLLMENT_NOT_FOUND", "Enrollment not found.", 404)
        if not enrollment.is_active:
            raise EnrollmentServiceError(
                "ENROLLMENT_INACTIVE", "Enrollment is not active.", 409
            )
        if enrollment.section_id == body.target_section_id:
            raise EnrollmentServiceError(
                "SAME_SECTION", "Student is already in the target section.", 409
            )

        # Validate target section
        target = (
            await db.execute(
                select(AcadSection).where(AcadSection.id == body.target_section_id)
            )
        ).scalar_one_or_none()
        if target is None:
            raise EnrollmentServiceError("SECTION_NOT_FOUND", "Target section not found.", 404)
        if not target.is_active:
            raise EnrollmentServiceError("SECTION_INACTIVE", "Target section is not active.", 409)

        # Capacity gate on target section
        from app.modules.m11_sis.capacity_service import CapacityError, CapacityService
        try:
            await CapacityService.check_capacity(body.target_section_id, db=db)
        except CapacityError as cap_err:
            raise EnrollmentServiceError(cap_err.code, cap_err.message, cap_err.status_code)

        # Fetch student email before the move for post-commit notification
        student = (
            await db.execute(select(User).where(User.id == enrollment.student_id))
        ).scalar_one_or_none()

        from_section_id = enrollment.section_id
        enrollment = await EnrollmentRepository.move(enrollment, body.target_section_id, db)
        await db.commit()

        await AuditService.log(
            AuditEventType.ENROLLMENT_MOVED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="acad_enrollment",
            target_id=str(enrollment_id),
            metadata={
                "student_id": str(enrollment.student_id),
                "from_section_id": str(from_section_id),
                "to_section_id": str(body.target_section_id),
            },
        )

        if student is not None:
            from app.core.notifications.models import NotificationType
            await _notify_safe(
                notification_type=NotificationType.ENROLLMENT_MOVED,
                recipient_user_id=student.id,
                recipient_email=student.email,
                title="Section Transfer",
                body=f"You have been moved to section \"{target.name}\".",
                entity_type="acad_enrollment",
                entity_id=str(enrollment_id),
                db=db,
            )

        return EnrollmentOut.model_validate(enrollment)

    @staticmethod
    async def list_students(
        db: AsyncSession,
        search: str | None = None,
    ) -> list[StudentSummaryOut]:
        return await EnrollmentRepository.list_students(db, search)

    @staticmethod
    async def get_student_profile(
        student_id: UUID,
        db: AsyncSession,
    ) -> StudentProfileOut:
        profile = await EnrollmentRepository.get_student_profile(student_id, db)
        if profile is None:
            raise EnrollmentServiceError("STUDENT_NOT_FOUND", "Student not found.", 404)
        return profile

    @staticmethod
    async def get_dashboard_counts(db: AsyncSession) -> DashboardCountsOut:
        return await EnrollmentRepository.get_dashboard_counts(db)
