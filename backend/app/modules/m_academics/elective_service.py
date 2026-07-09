from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m_academics.assignment_schemas import AssignmentCreate
from app.modules.m_academics.assignment_service import (
    AssignmentService,
    AssignmentServiceError,
)
from app.modules.m_academics.dean_scope import (
    assert_dean_owns_semester_program,
    get_dean_program_ids,
    get_semester_program_id,
)
from app.modules.m_academics.elective_models import (
    ElectiveOffering,
    ElectiveOfferingStatus,
    ElectiveRegistration,
    ElectiveRegistrationStatus,
)
from app.modules.m_academics.models import CourseRoleInCourse
from app.modules.m_academics.service import AcadServiceError

# Faculty for each elective course is resolved from an active PRIMARY Course
# Assignment (subject_assignments) — the same source attendance and internal
# marks already key off, so assigning faculty here makes Steps 7/8 integrate
# with no extra plumbing.
_FACULTY_JOIN_SQL = """
    LEFT JOIN LATERAL (
        SELECT u.id AS faculty_user_id, u.full_name
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
    # Dean — offering lifecycle (create / edit / open-close) + faculty
    # assignment. There is NO propose/approve/publish path: electives are
    # a Dean academic-authority responsibility end to end. Faculty never
    # create, propose, or approve offerings — they only teach what the
    # Dean assigns them.
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
    async def _assert_course_in_basket(course_id: UUID, basket_id: UUID, db: AsyncSession) -> None:
        row = (await db.execute(text(
            "SELECT 1 FROM courses WHERE id = :course_id AND elective_basket_id = :basket_id"
        ), {"course_id": str(course_id), "basket_id": str(basket_id)})).first()
        if row is None:
            raise AcadServiceError(
                "COURSE_NOT_IN_BASKET", "That course is not part of this elective basket.", 400,
            )

    @staticmethod
    async def _assign_course_faculty(
        course_id: UUID,
        semester_id: UUID,
        faculty_user_id: UUID,
        *,
        assigned_by: UUID,
        actor_role: str,
        tenant_id: UUID | None,
        schema_name: str | None,
        db: AsyncSession,
    ) -> None:
        """Make `faculty_user_id` the PRIMARY faculty for this elective course
        in this semester, reusing the Subject Assignment workflow (which audits,
        notifies, and enforces dean scope + faculty-role validity). Idempotent:
        if the same faculty is already PRIMARY it is a no-op; if a different
        faculty is PRIMARY it is revoked and replaced (the Dean reassigning)."""
        from app.modules.m_academics.assignment_repository import SubjectAssignmentRepository

        existing = await SubjectAssignmentRepository.list_by_course(
            course_id, semester_id=semester_id, db=db,
        )
        primary = next(
            (a for a in existing if a.role_in_course == CourseRoleInCourse.PRIMARY and a.is_active),
            None,
        )
        if primary is not None:
            if primary.faculty_user_id == faculty_user_id:
                return  # already the assigned faculty — nothing to do
            await AssignmentService.revoke(
                primary.id,
                revoked_by=assigned_by,
                actor_role=actor_role,
                tenant_id=tenant_id,
                schema_name=schema_name,
                db=db,
            )

        await AssignmentService.create(
            AssignmentCreate(
                course_id=course_id,
                faculty_user_id=faculty_user_id,
                semester_id=semester_id,
                role_in_course=CourseRoleInCourse.PRIMARY,
            ),
            assigned_by=assigned_by,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            db=db,
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
                       fac.faculty_user_id, fac.full_name AS faculty_name
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
        courses, each with a per-course seats_taken count and the Dean-assigned
        faculty (via the active PRIMARY Course Assignment)."""
        out = []
        for r in rows:
            course_rows = (await db.execute(text(
                f"""
                SELECT c.id AS course_id, c.code, c.title, c.credits, c.description,
                       fac.faculty_user_id, fac.full_name AS faculty_name,
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
    async def create_offering(body, created_by: UUID, db: AsyncSession, *,
                              actor_role: str = "DEAN",
                              tenant_id: UUID | None = None,
                              schema_name: str | None = None) -> ElectiveOffering:
        # Ownership: a Dean may only create offerings for a semester whose
        # program they govern.
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

        # Assign the faculty the Dean chose for each course in the basket.
        for fa in (body.faculty_assignments or []):
            await ElectiveService._assert_course_in_basket(fa.course_id, body.basket_id, db)
            try:
                await ElectiveService._assign_course_faculty(
                    fa.course_id, body.semester_id, fa.faculty_user_id,
                    assigned_by=created_by, actor_role=actor_role,
                    tenant_id=tenant_id, schema_name=schema_name, db=db,
                )
            except AssignmentServiceError as e:
                raise AcadServiceError(e.code, e.message, e.status_code)

        return offering

    @staticmethod
    async def assign_faculty(
        offering_id: UUID, course_id: UUID, faculty_user_id: UUID, dean_id: UUID,
        db: AsyncSession, *, actor_role: str = "DEAN",
        tenant_id: UUID | None = None, schema_name: str | None = None,
    ) -> ElectiveOffering:
        offering = await ElectiveService._load(offering_id, db)
        await assert_dean_owns_semester_program(
            dean_id, offering.semester_id, db, "Elective offering not found.",
        )
        await ElectiveService._assert_course_in_basket(course_id, offering.basket_id, db)
        try:
            await ElectiveService._assign_course_faculty(
                course_id, offering.semester_id, faculty_user_id,
                assigned_by=dean_id, actor_role=actor_role,
                tenant_id=tenant_id, schema_name=schema_name, db=db,
            )
        except AssignmentServiceError as e:
            raise AcadServiceError(e.code, e.message, e.status_code)
        return offering

    @staticmethod
    async def _dean_program_filter(dean_id: UUID | None, actor_role: str | None, db: AsyncSession):
        """Return (sql_fragment, params) restricting offerings to a Dean's
        governed programs, or ('', {}) for unrestricted (ADMIN) callers."""
        if actor_role != "DEAN" or dean_id is None:
            return "", {}
        governed = await get_dean_program_ids(dean_id, "DEAN", db)
        if governed is None:
            return "", {}
        if not governed:
            return "AND false", {}
        return (
            "AND p.acad_program_id = ANY(:governed_programs)",
            {"governed_programs": [str(g) for g in governed]},
        )

    @staticmethod
    async def list_offerings_admin(
        db: AsyncSession, semester_id: UUID | None = None,
        *, dean_id: UUID | None = None, actor_role: str | None = None,
    ) -> list[dict]:
        scope_sql, scope_params = await ElectiveService._dean_program_filter(dean_id, actor_role, db)
        sql = f"""
            SELECT eo.*, b.name AS basket_name, b.description AS basket_description
            FROM elective_offerings eo
            JOIN elective_baskets b ON b.id = eo.basket_id
            JOIN programs p ON p.id = b.program_id
            WHERE (:semester_id IS NULL OR eo.semester_id = :semester_id)
            {scope_sql}
            ORDER BY eo.created_at DESC
        """
        rows = (await db.execute(text(sql), {
            "semester_id": str(semester_id) if semester_id else None,
            **scope_params,
        })).mappings().all()
        return await ElectiveService._attach_courses([dict(r) for r in rows], db)

    @staticmethod
    async def get_dashboard_stats(
        db: AsyncSession, semester_id: UUID | None = None,
        *, dean_id: UUID | None = None, actor_role: str | None = None,
    ) -> dict:
        """Live demand statistics for the Dean: every OPEN/CLOSED offering with
        per-course registration counts, plus rolled-up totals."""
        offerings = await ElectiveService.list_offerings_admin(
            db, semester_id=semester_id, dean_id=dean_id, actor_role=actor_role,
        )
        total_registrations = sum(
            c["seats_taken"] for o in offerings for c in o["courses"]
        )
        return {
            "total_offerings": len(offerings),
            "total_registrations": total_registrations,
            "offerings": offerings,
        }

    @staticmethod
    async def _load(offering_id: UUID, db: AsyncSession) -> ElectiveOffering:
        offering = (await db.execute(
            select(ElectiveOffering).where(ElectiveOffering.id == offering_id)
        )).scalar_one_or_none()
        if offering is None:
            raise AcadServiceError("OFFERING_NOT_FOUND", "Elective offering not found.", 404)
        return offering

    @staticmethod
    async def update_offering(offering_id: UUID, dean_id: UUID, body, db: AsyncSession) -> ElectiveOffering:
        offering = await ElectiveService._load(offering_id, db)
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
    # Faculty — read-only. A faculty member sees ONLY the students who
    # registered for the elective(s) the Dean assigned them to teach.
    # -----------------------------------------------------------------

    @staticmethod
    async def get_faculty_elective_roster(faculty_id: UUID, db: AsyncSession) -> list[dict]:
        """Every elective course this faculty is the active PRIMARY/CO_FACULTY
        for that has an open offering, each with the list of students who
        registered for THAT course (never students of a sibling elective)."""
        rows = (await db.execute(text("""
            SELECT
                c.id::text          AS course_id,
                c.code              AS course_code,
                c.title             AS course_title,
                eo.id::text         AS offering_id,
                eo.semester_id::text AS semester_id,
                COALESCE(sem.label, CONCAT('Semester ', sem.number)) AS semester_label,
                b.name              AS basket_name,
                er.student_user_id::text AS student_id,
                u.full_name         AS student_name,
                sp.usn              AS usn,
                u.email             AS student_email,
                er.registered_at    AS registered_at
            FROM elective_registrations er
            JOIN elective_offerings eo ON eo.id = er.offering_id
            JOIN elective_baskets   b  ON b.id = eo.basket_id
            JOIN courses c             ON c.id = er.course_id
            JOIN acad_semesters sem    ON sem.id = eo.semester_id
            JOIN subject_assignments sa ON sa.course_id = er.course_id
                                       AND sa.semester_id = eo.semester_id
                                       AND sa.faculty_user_id = :faculty_id
                                       AND sa.is_active = true
                                       AND sa.role_in_course IN ('PRIMARY', 'CO_FACULTY')
            JOIN users u               ON u.id = er.student_user_id
            LEFT JOIN sis_student_profiles sp ON sp.user_id = er.student_user_id
            WHERE er.status = 'REGISTERED'
            ORDER BY c.title, u.full_name
        """), {"faculty_id": str(faculty_id)})).mappings().all()

        by_course: dict[str, dict] = {}
        for r in rows:
            key = r["course_id"]
            group = by_course.setdefault(key, {
                "course_id": r["course_id"],
                "course_code": r["course_code"],
                "course_title": r["course_title"],
                "offering_id": r["offering_id"],
                "semester_id": r["semester_id"],
                "semester_label": r["semester_label"],
                "basket_name": r["basket_name"],
                "students": [],
            })
            group["students"].append({
                "student_id": r["student_id"],
                "student_name": r["student_name"],
                "usn": r["usn"],
                "student_email": r["student_email"],
                "registered_at": r["registered_at"],
            })
        result = list(by_course.values())
        for g in result:
            g["total_students"] = len(g["students"])
        return result

    # -----------------------------------------------------------------
    # Student — sees only electives available for their own program +
    # semester; registers for ONE course from a basket.
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
