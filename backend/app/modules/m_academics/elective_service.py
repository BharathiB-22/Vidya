from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m_academics.dean_scope import assert_dean_owns_semester_program, get_semester_program_id
from app.modules.m_academics.elective_models import (
    ElectiveOffering,
    ElectiveOfferingStatus,
    ElectiveRegistration,
    ElectiveRegistrationStatus,
)
from app.modules.m_academics.service import AcadServiceError

_FACULTY_JOIN_SQL = """
    LEFT JOIN LATERAL (
        SELECT u.full_name
        FROM subject_assignments sa
        JOIN users u ON u.id = sa.faculty_user_id
        WHERE sa.course_id = c.id AND sa.semester_id = :semester_id
          AND sa.is_active = true AND sa.role_in_course = 'PRIMARY'
        LIMIT 1
    ) fac ON true
"""


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
    async def _assert_basket_eligible_for_semester(
        basket_id: UUID, semester_id: UUID, db: AsyncSession,
    ) -> None:
        """A basket may only be offered against a semester belonging to the
        same Published curriculum program the basket was defined in, and
        must contain at least one course -- closes the gap where a Dean
        could open an empty basket, a basket from a different program's
        batch, or one from a still-DRAFT/Approved-but-unpublished program."""
        basket = (await db.execute(text(
            "SELECT id, program_id FROM elective_baskets WHERE id = :id"
        ), {"id": str(basket_id)})).mappings().first()
        if basket is None:
            raise AcadServiceError("BASKET_NOT_FOUND", "Elective basket not found.", 404)

        program_row = (await db.execute(text(
            "SELECT acad_program_id, status FROM programs WHERE id = :id"
        ), {"id": str(basket["program_id"])})).mappings().first()
        if program_row is None or program_row["status"] != "PUBLISHED":
            raise AcadServiceError(
                "PROGRAM_NOT_PUBLISHED",
                "This basket's program has not been published by the Dean yet.", 400,
            )

        semester_program_id = await get_semester_program_id(semester_id, db)
        if semester_program_id is None or program_row["acad_program_id"] != semester_program_id:
            raise AcadServiceError(
                "SEMESTER_PROGRAM_MISMATCH",
                "This basket does not belong to the selected semester's program.", 400,
            )

        course_count = (await db.execute(text(
            "SELECT COUNT(*) FROM courses WHERE elective_basket_id = :id"
        ), {"id": str(basket_id)})).scalar_one()
        if course_count == 0:
            raise AcadServiceError(
                "BASKET_EMPTY", "This basket has no elective courses in it yet.", 400,
            )

    @staticmethod
    async def list_eligible_baskets(semester_id: UUID, db: AsyncSession) -> list[dict]:
        """Elective baskets auto-eligible for an offering in `semester_id`:
        defined in the semester's own Published curriculum program, at that
        semester's curriculum semester number. This is what the Dean picks
        from -- never a free-text course name, and never a single course."""
        sem_row = (await db.execute(text(
            "SELECT number FROM acad_semesters WHERE id = :id"
        ), {"id": str(semester_id)})).mappings().first()
        if sem_row is None:
            raise AcadServiceError("SEMESTER_NOT_FOUND", "Semester not found.", 404)

        acad_program_id = await get_semester_program_id(semester_id, db)
        if acad_program_id is None:
            return []

        basket_rows = (await db.execute(text(
            f"""
            SELECT b.id AS basket_id, b.name, b.description,
                   EXISTS (
                       SELECT 1 FROM elective_offerings eo
                       WHERE eo.basket_id = b.id AND eo.semester_id = :semester_id
                   ) AS already_offered
            FROM elective_baskets b
            JOIN programs p ON p.id = b.program_id
            WHERE p.acad_program_id = :acad_program_id
              AND p.status = 'PUBLISHED'
              AND b.semester = :semester_number
            ORDER BY b.name
            """
        ), {
            "semester_id": str(semester_id),
            "acad_program_id": str(acad_program_id),
            "semester_number": sem_row["number"],
        })).mappings().all()

        baskets = []
        for b in basket_rows:
            course_rows = (await db.execute(text(
                f"""
                SELECT c.id AS course_id, c.code, c.title, c.credits, c.description,
                       fac.full_name AS faculty_name
                FROM courses c
                {_FACULTY_JOIN_SQL}
                WHERE c.elective_basket_id = :basket_id
                ORDER BY c.title
                """
            ), {"basket_id": str(b["basket_id"]), "semester_id": str(semester_id)})).mappings().all()
            baskets.append({**dict(b), "courses": [dict(c) for c in course_rows]})
        return baskets

    @staticmethod
    async def _attach_courses(rows: list[dict], db: AsyncSession) -> list[dict]:
        """Populate each offering row's `courses` list -- the basket's member
        courses, each with a per-course seats_taken count and best-effort
        resolved faculty (via an active PRIMARY Course Assignment)."""
        out = []
        for r in rows:
            course_rows = (await db.execute(text(
                f"""
                SELECT c.id AS course_id, c.code, c.title, c.credits, c.description,
                       fac.full_name AS faculty_name,
                       (SELECT COUNT(*) FROM elective_registrations er
                         WHERE er.offering_id = :offering_id AND er.course_id = c.id
                           AND er.status = 'REGISTERED') AS seats_taken
                FROM courses c
                {_FACULTY_JOIN_SQL}
                WHERE c.elective_basket_id = :basket_id
                ORDER BY c.title
                """
            ), {
                "basket_id": str(r["basket_id"]), "semester_id": str(r["semester_id"]),
                "offering_id": str(r["id"]),
            })).mappings().all()
            out.append({**r, "courses": [dict(c) for c in course_rows]})
        return out

    @staticmethod
    async def create_offering(body, created_by: UUID, db: AsyncSession) -> ElectiveOffering:
        # Ownership: a Dean may only create offerings for a semester whose
        # program they govern (closes the loophole of bypassing the
        # propose->approve chain to create directly in another department).
        await assert_dean_owns_semester_program(
            created_by, body.semester_id, db, "Semester not found in your governed programs.",
        )
        await ElectiveService._assert_basket_eligible_for_semester(body.basket_id, body.semester_id, db)

        offering = ElectiveOffering(
            id=uuid.uuid4(),
            basket_id=body.basket_id, semester_id=body.semester_id,
            max_seats=body.max_seats,
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
            SELECT eo.*, b.name AS basket_name, b.description AS basket_description
            FROM elective_offerings eo
            JOIN elective_baskets b ON b.id = eo.basket_id
            WHERE (:semester_id IS NULL OR eo.semester_id = :semester_id)
            ORDER BY eo.created_at DESC
        """
        rows = (await db.execute(text(sql), {
            "semester_id": str(semester_id) if semester_id else None,
        })).mappings().all()
        return await ElectiveService._attach_courses([dict(r) for r in rows], db)

    # -----------------------------------------------------------------
    # Faculty propose -> Dean approve/reject -> Dean publish
    # -----------------------------------------------------------------

    @staticmethod
    async def propose_offering(body, proposed_by: UUID, db: AsyncSession) -> ElectiveOffering:
        await ElectiveService._assert_basket_eligible_for_semester(body.basket_id, body.semester_id, db)

        offering = ElectiveOffering(
            id=uuid.uuid4(),
            basket_id=body.basket_id, semester_id=body.semester_id,
            max_seats=body.max_seats,
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
            SELECT eo.*, b.name AS basket_name, b.description AS basket_description
            FROM elective_offerings eo
            JOIN elective_baskets b ON b.id = eo.basket_id
            WHERE eo.proposed_by_user_id = :faculty_id
            ORDER BY eo.created_at DESC
        """
        rows = (await db.execute(text(sql), {"faculty_id": str(faculty_id)})).mappings().all()
        return await ElectiveService._attach_courses([dict(r) for r in rows], db)

    @staticmethod
    async def _list_by_status(db: AsyncSession, status: str) -> list[dict]:
        sql = """
            SELECT eo.*, b.name AS basket_name, b.description AS basket_description
            FROM elective_offerings eo
            JOIN elective_baskets b ON b.id = eo.basket_id
            WHERE eo.status = :status
            ORDER BY eo.created_at DESC
        """
        rows = (await db.execute(text(sql), {"status": status})).mappings().all()
        return await ElectiveService._attach_courses([dict(r) for r in rows], db)

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
            SELECT eo.*, b.name AS basket_name, b.description AS basket_description
            FROM elective_offerings eo
            JOIN elective_baskets b ON b.id = eo.basket_id
            WHERE eo.status = 'OPEN'
              AND (:semester_id IS NULL OR eo.semester_id = :semester_id)
            ORDER BY b.name
        """
        rows = (await db.execute(text(sql), {
            "semester_id": str(target_semester) if target_semester else None,
        })).mappings().all()
        return await ElectiveService._attach_courses([dict(r) for r in rows], db)

    @staticmethod
    async def register(offering_id: UUID, course_id: UUID, student_id: UUID, db: AsyncSession) -> ElectiveRegistration:
        offering = (await db.execute(
            select(ElectiveOffering).where(ElectiveOffering.id == offering_id)
        )).scalar_one_or_none()
        if offering is None:
            raise AcadServiceError("OFFERING_NOT_FOUND", "Elective offering not found.", 404)
        if offering.status != ElectiveOfferingStatus.OPEN.value:
            raise AcadServiceError("OFFERING_CLOSED", "Registration for this elective is closed.", 400)

        course_in_basket = (await db.execute(text(
            "SELECT 1 FROM courses WHERE id = :course_id AND elective_basket_id = :basket_id"
        ), {"course_id": str(course_id), "basket_id": str(offering.basket_id)})).first()
        if course_in_basket is None:
            raise AcadServiceError(
                "COURSE_NOT_IN_BASKET", "That course is not part of this elective basket.", 400,
            )

        seats_taken = (await db.execute(text(
            "SELECT COUNT(*) FROM elective_registrations "
            "WHERE offering_id = :id AND course_id = :course_id AND status = 'REGISTERED'"
        ), {"id": str(offering_id), "course_id": str(course_id)})).scalar_one()
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
                raise AcadServiceError("ALREADY_REGISTERED", "Already registered for an elective in this basket.", 409)
            existing.course_id = course_id
            existing.status = new_status
            existing.registered_at = datetime.utcnow()
            reg = existing
        else:
            reg = ElectiveRegistration(
                id=uuid.uuid4(), offering_id=offering_id, course_id=course_id,
                student_user_id=student_id, status=new_status,
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
                   eo.basket_id, eo.semester_id, b.name AS basket_name,
                   c.id AS course_id, c.code AS course_code, c.title AS course_title, c.credits,
                   COALESCE(sem.label, CONCAT('Semester ', sem.number)) AS semester_label
            FROM elective_registrations er
            JOIN elective_offerings eo ON eo.id = er.offering_id
            JOIN elective_baskets b ON b.id = eo.basket_id
            JOIN courses c ON c.id = er.course_id
            JOIN acad_semesters sem ON sem.id = eo.semester_id
            WHERE er.student_user_id = :student_id
            ORDER BY er.registered_at DESC
        """
        rows = (await db.execute(text(sql), {"student_id": str(student_id)})).mappings().all()
        return [
            {**dict(r), "is_current": current_semester is not None and r["semester_id"] == current_semester}
            for r in rows
        ]
