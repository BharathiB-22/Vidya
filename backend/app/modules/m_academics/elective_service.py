from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m_academics.dean_scope import assert_dean_owns_semester_program
from app.modules.m_academics.elective_models import (
    ElectiveOffering,
    ElectiveOfferingStatus,
    ElectiveRegistration,
    ElectiveRegistrationStatus,
)
from app.modules.m_academics.service import AcadServiceError


async def _get_student_current_semester_id(student_id: UUID, db: AsyncSession) -> UUID | None:
    row = (await db.execute(text("""
        SELECT sem.id
        FROM acad_enrollments ae
        JOIN acad_sections s ON s.id = ae.section_id
        JOIN acad_semesters sem ON sem.id = s.semester_id
        WHERE ae.student_id = :student_id AND ae.is_active = true
    """), {"student_id": str(student_id)})).first()
    return row[0] if row else None


class ElectiveService:
    # -----------------------------------------------------------------
    # Admin/Dean
    # -----------------------------------------------------------------

    @staticmethod
    async def create_offering(body, created_by: UUID, db: AsyncSession) -> ElectiveOffering:
        # Ownership: a Dean may only create offerings for a semester whose
        # program they govern (closes the loophole of bypassing the
        # propose->approve chain to create directly in another department).
        await assert_dean_owns_semester_program(
            created_by, body.semester_id, db, "Semester not found in your governed programs.",
        )

        course = (await db.execute(text(
            "SELECT id, is_elective FROM courses WHERE id = :id"
        ), {"id": str(body.course_id)})).mappings().first()
        if course is None:
            raise AcadServiceError("COURSE_NOT_FOUND", "Course not found.", 404)
        if not course["is_elective"]:
            raise AcadServiceError("NOT_ELECTIVE", "This course is not marked as an elective.", 400)

        offering = ElectiveOffering(
            id=uuid.uuid4(),
            course_id=body.course_id, semester_id=body.semester_id,
            faculty_user_id=body.faculty_user_id, max_seats=body.max_seats,
            registration_opens_at=body.registration_opens_at,
            registration_closes_at=body.registration_closes_at,
            status=ElectiveOfferingStatus.OPEN.value,
            created_by_user_id=created_by,
        )
        db.add(offering)
        await db.commit()
        await db.refresh(offering)
        return offering

    @staticmethod
    async def list_offerings_admin(db: AsyncSession, semester_id: UUID | None = None) -> list[dict]:
        sql = """
            SELECT eo.*, c.code AS course_code, c.title AS course_title, c.credits, c.description,
                   u.full_name AS faculty_name,
                   (SELECT COUNT(*) FROM elective_registrations er
                     WHERE er.offering_id = eo.id AND er.status = 'REGISTERED') AS seats_taken
            FROM elective_offerings eo
            JOIN courses c ON c.id = eo.course_id
            LEFT JOIN users u ON u.id = eo.faculty_user_id
            WHERE (:semester_id IS NULL OR eo.semester_id = :semester_id)
            ORDER BY eo.created_at DESC
        """
        rows = (await db.execute(text(sql), {
            "semester_id": str(semester_id) if semester_id else None,
        })).mappings().all()
        return [dict(r) for r in rows]

    # -----------------------------------------------------------------
    # Faculty propose -> Dean approve/reject -> Admin publish
    # -----------------------------------------------------------------

    @staticmethod
    async def propose_offering(body, proposed_by: UUID, db: AsyncSession) -> ElectiveOffering:
        course = (await db.execute(text(
            "SELECT id, is_elective FROM courses WHERE id = :id"
        ), {"id": str(body.course_id)})).mappings().first()
        if course is None:
            raise AcadServiceError("COURSE_NOT_FOUND", "Course not found.", 404)
        if not course["is_elective"]:
            raise AcadServiceError("NOT_ELECTIVE", "This course is not marked as an elective.", 400)

        offering = ElectiveOffering(
            id=uuid.uuid4(),
            course_id=body.course_id, semester_id=body.semester_id,
            faculty_user_id=proposed_by, max_seats=body.max_seats,
            registration_opens_at=body.registration_opens_at,
            registration_closes_at=body.registration_closes_at,
            status=ElectiveOfferingStatus.PROPOSED.value,
            created_by_user_id=proposed_by,
            proposed_by_user_id=proposed_by,
        )
        db.add(offering)
        await db.commit()
        await db.refresh(offering)
        return offering

    @staticmethod
    async def list_mine_for_faculty(faculty_id: UUID, db: AsyncSession) -> list[dict]:
        sql = """
            SELECT eo.*, c.code AS course_code, c.title AS course_title, c.credits, c.description,
                   u.full_name AS faculty_name,
                   (SELECT COUNT(*) FROM elective_registrations er
                     WHERE er.offering_id = eo.id AND er.status = 'REGISTERED') AS seats_taken
            FROM elective_offerings eo
            JOIN courses c ON c.id = eo.course_id
            LEFT JOIN users u ON u.id = eo.faculty_user_id
            WHERE eo.proposed_by_user_id = :faculty_id
            ORDER BY eo.created_at DESC
        """
        rows = (await db.execute(text(sql), {"faculty_id": str(faculty_id)})).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    async def _list_by_status(db: AsyncSession, status: str) -> list[dict]:
        sql = """
            SELECT eo.*, c.code AS course_code, c.title AS course_title, c.credits, c.description,
                   u.full_name AS faculty_name,
                   (SELECT COUNT(*) FROM elective_registrations er
                     WHERE er.offering_id = eo.id AND er.status = 'REGISTERED') AS seats_taken
            FROM elective_offerings eo
            JOIN courses c ON c.id = eo.course_id
            LEFT JOIN users u ON u.id = eo.faculty_user_id
            WHERE eo.status = :status
            ORDER BY eo.created_at DESC
        """
        rows = (await db.execute(text(sql), {"status": status})).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    async def list_pending_for_dean(db: AsyncSession) -> list[dict]:
        return await ElectiveService._list_by_status(db, ElectiveOfferingStatus.PROPOSED.value)

    @staticmethod
    async def list_approved_for_admin(db: AsyncSession) -> list[dict]:
        return await ElectiveService._list_by_status(db, ElectiveOfferingStatus.DEAN_APPROVED.value)

    @staticmethod
    async def _load(offering_id: UUID, db: AsyncSession) -> ElectiveOffering:
        offering = (await db.execute(
            select(ElectiveOffering).where(ElectiveOffering.id == offering_id)
        )).scalar_one_or_none()
        if offering is None:
            raise AcadServiceError("OFFERING_NOT_FOUND", "Elective offering not found.", 404)
        return offering

    @staticmethod
    async def approve_offering(offering_id: UUID, dean_id: UUID, db: AsyncSession) -> ElectiveOffering:
        offering = await ElectiveService._load(offering_id, db)
        await assert_dean_owns_semester_program(
            dean_id, offering.semester_id, db, "Elective offering not found.",
        )
        if offering.status != ElectiveOfferingStatus.PROPOSED.value:
            raise AcadServiceError("INVALID_STATUS", "Only proposed offerings can be approved.", 400)
        offering.status = ElectiveOfferingStatus.DEAN_APPROVED.value
        offering.approved_by_user_id = dean_id
        offering.approved_at = datetime.utcnow()
        offering.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(offering)
        return offering

    @staticmethod
    async def reject_offering(offering_id: UUID, dean_id: UUID, reason: str, db: AsyncSession) -> ElectiveOffering:
        offering = await ElectiveService._load(offering_id, db)
        await assert_dean_owns_semester_program(
            dean_id, offering.semester_id, db, "Elective offering not found.",
        )
        if offering.status != ElectiveOfferingStatus.PROPOSED.value:
            raise AcadServiceError("INVALID_STATUS", "Only proposed offerings can be rejected.", 400)
        offering.status = ElectiveOfferingStatus.REJECTED.value
        offering.rejection_reason = reason
        offering.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(offering)
        return offering

    @staticmethod
    async def publish_offering(offering_id: UUID, dean_id: UUID, db: AsyncSession) -> ElectiveOffering:
        offering = await ElectiveService._load(offering_id, db)
        await assert_dean_owns_semester_program(
            dean_id, offering.semester_id, db, "Elective offering not found.",
        )
        if offering.status != ElectiveOfferingStatus.DEAN_APPROVED.value:
            raise AcadServiceError("INVALID_STATUS", "Only dean-approved offerings can be published.", 400)
        offering.status = ElectiveOfferingStatus.OPEN.value
        offering.published_by_user_id = dean_id
        offering.published_at = datetime.utcnow()
        offering.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(offering)
        return offering

    @staticmethod
    async def update_offering(offering_id: UUID, dean_id: UUID, body, db: AsyncSession) -> ElectiveOffering:
        offering = (await db.execute(
            select(ElectiveOffering).where(ElectiveOffering.id == offering_id)
        )).scalar_one_or_none()
        if offering is None:
            raise AcadServiceError("OFFERING_NOT_FOUND", "Elective offering not found.", 404)
        await assert_dean_owns_semester_program(
            dean_id, offering.semester_id, db, "Elective offering not found.",
        )
        data = body.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(offering, field, value)
        offering.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(offering)
        return offering

    # -----------------------------------------------------------------
    # Student
    # -----------------------------------------------------------------

    @staticmethod
    async def list_available_for_student(
        student_id: UUID, db: AsyncSession, semester_id: UUID | None = None
    ) -> list[dict]:
        target_semester = semester_id or await _get_student_current_semester_id(student_id, db)
        sql = """
            SELECT eo.*, c.code AS course_code, c.title AS course_title, c.credits, c.description,
                   u.full_name AS faculty_name,
                   (SELECT COUNT(*) FROM elective_registrations er
                     WHERE er.offering_id = eo.id AND er.status = 'REGISTERED') AS seats_taken
            FROM elective_offerings eo
            JOIN courses c ON c.id = eo.course_id
            LEFT JOIN users u ON u.id = eo.faculty_user_id
            WHERE eo.status = 'OPEN'
              AND (:semester_id IS NULL OR eo.semester_id = :semester_id)
            ORDER BY c.title
        """
        rows = (await db.execute(text(sql), {
            "semester_id": str(target_semester) if target_semester else None,
        })).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    async def register(offering_id: UUID, student_id: UUID, db: AsyncSession) -> ElectiveRegistration:
        offering = (await db.execute(
            select(ElectiveOffering).where(ElectiveOffering.id == offering_id)
        )).scalar_one_or_none()
        if offering is None:
            raise AcadServiceError("OFFERING_NOT_FOUND", "Elective offering not found.", 404)
        if offering.status != ElectiveOfferingStatus.OPEN.value:
            raise AcadServiceError("OFFERING_CLOSED", "Registration for this elective is closed.", 400)

        seats_taken = (await db.execute(text(
            "SELECT COUNT(*) FROM elective_registrations WHERE offering_id = :id AND status = 'REGISTERED'"
        ), {"id": str(offering_id)})).scalar_one()
        new_status = (
            ElectiveRegistrationStatus.REGISTERED.value
            if seats_taken < offering.max_seats
            else ElectiveRegistrationStatus.WAITLISTED.value
        )

        existing = (await db.execute(
            select(ElectiveRegistration).where(
                ElectiveRegistration.offering_id == offering_id,
                ElectiveRegistration.student_user_id == student_id,
            )
        )).scalar_one_or_none()
        if existing is not None:
            if existing.status == ElectiveRegistrationStatus.REGISTERED.value:
                raise AcadServiceError("ALREADY_REGISTERED", "Already registered for this elective.", 409)
            existing.status = new_status
            existing.registered_at = datetime.utcnow()
            reg = existing
        else:
            reg = ElectiveRegistration(
                id=uuid.uuid4(), offering_id=offering_id, student_user_id=student_id,
                status=new_status,
            )
            db.add(reg)
        await db.commit()
        await db.refresh(reg)
        return reg

    @staticmethod
    async def drop(offering_id: UUID, student_id: UUID, db: AsyncSession) -> ElectiveRegistration:
        reg = (await db.execute(
            select(ElectiveRegistration).where(
                ElectiveRegistration.offering_id == offering_id,
                ElectiveRegistration.student_user_id == student_id,
            )
        )).scalar_one_or_none()
        if reg is None:
            raise AcadServiceError("REGISTRATION_NOT_FOUND", "No registration found for this elective.", 404)
        reg.status = ElectiveRegistrationStatus.DROPPED.value
        reg.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(reg)
        return reg

    @staticmethod
    async def get_my_registrations(student_id: UUID, db: AsyncSession) -> list[dict]:
        current_semester = await _get_student_current_semester_id(student_id, db)
        sql = """
            SELECT er.id, er.offering_id, er.status, er.registered_at,
                   eo.course_id, eo.semester_id, eo.faculty_user_id,
                   c.code AS course_code, c.title AS course_title, c.credits,
                   COALESCE(sem.label, CONCAT('Semester ', sem.number)) AS semester_label,
                   u.full_name AS faculty_name
            FROM elective_registrations er
            JOIN elective_offerings eo ON eo.id = er.offering_id
            JOIN courses c ON c.id = eo.course_id
            JOIN acad_semesters sem ON sem.id = eo.semester_id
            LEFT JOIN users u ON u.id = eo.faculty_user_id
            WHERE er.student_user_id = :student_id
            ORDER BY er.registered_at DESC
        """
        rows = (await db.execute(text(sql), {"student_id": str(student_id)})).mappings().all()
        return [
            {**dict(r), "is_current": current_semester is not None and r["semester_id"] == current_semester}
            for r in rows
        ]
