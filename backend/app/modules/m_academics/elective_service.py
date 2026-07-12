"""Elective registration and per-term faculty assignment.

The curriculum slot is the single source of truth. A slot is visible to students
once PUBLISHED, registerable while OPEN, and frozen once CLOSED — see
`m01_program_advisor.models.ElectiveSlotStatus`. There is no offering to create.

Curriculum and teaching are separate axes. The slot and its choices are fixed
curriculum: MCA Semester 3, Elective 1, offering AI/ML/DL. *Who teaches* each
choice is a per-term fact, so Odd-2026 may have Dr Ravi on AI and Odd-2027
Dr Priya, with the curriculum untouched. That is why faculty assignment is keyed
on `(course_id, semester_id)` in `subject_assignments` — the same source
attendance and internal marks read, which is what makes an elective's combined
class work with no elective-specific plumbing.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m01_program_advisor.models import ElectiveSlotStatus
from app.modules.m_academics.assignment_schemas import AssignmentCreate
from app.modules.m_academics.assignment_service import (
    AssignmentService,
    AssignmentServiceError,
)
from app.modules.m_academics.dean_scope import assert_dean_owns_semester_program
from app.modules.m_academics.elective_models import (
    ElectiveRegistration,
    ElectiveRegistrationStatus,
)
from app.modules.m_academics.models import CourseRoleInCourse
from app.modules.m_academics.service import AcadServiceError

# Slots students can see at all. A DRAFT slot is still being assembled.
_STUDENT_VISIBLE = (
    ElectiveSlotStatus.PUBLISHED.value,
    ElectiveSlotStatus.OPEN.value,
    ElectiveSlotStatus.CLOSED.value,
)

# The faculty teaching each option in a given term, via the active PRIMARY
# Course Assignment — the same source attendance and marks key off.
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


class _StudentTerm:
    """Where a student currently sits: the running term, its curriculum
    semester number, and the institutional program their batch belongs to."""

    __slots__ = ("semester_id", "semester_number", "acad_program_id")

    def __init__(self, semester_id: UUID, semester_number: int, acad_program_id: UUID) -> None:
        self.semester_id = semester_id
        self.semester_number = semester_number
        self.acad_program_id = acad_program_id


async def _get_student_term(student_id: UUID, db: AsyncSession) -> _StudentTerm | None:
    row = (await db.execute(text("""
        SELECT sem.id AS semester_id, sem.number AS semester_number,
               b.program_id AS acad_program_id
        FROM acad_enrollments ae
        JOIN acad_sections  s   ON s.id   = ae.section_id
        JOIN acad_semesters sem ON sem.id = s.semester_id
        JOIN acad_batches   b   ON b.id   = sem.batch_id
        WHERE ae.student_id = :student_id AND ae.is_active = true
        LIMIT 1
    """), {"student_id": str(student_id)})).mappings().first()
    if row is None:
        return None
    return _StudentTerm(row["semester_id"], row["semester_number"], row["acad_program_id"])


class ElectiveService:
    # -----------------------------------------------------------------
    # Shared slot/option reads
    # -----------------------------------------------------------------

    @staticmethod
    async def _options_for_baskets(
        basket_ids: list[UUID], semester_id: UUID, db: AsyncSession,
    ) -> dict[str, list[dict]]:
        """Every option course hanging off each slot, with the faculty assigned
        for `semester_id` and how many students have chosen it."""
        if not basket_ids:
            return {}

        rows = (await db.execute(text(f"""
            SELECT c.elective_basket_id::text AS basket_id,
                   c.id AS course_id, c.code, c.title, c.credits,
                   c.course_type, c.description,
                   fac.faculty_user_id, fac.full_name AS faculty_name,
                   (SELECT COUNT(*) FROM elective_registrations er
                     WHERE er.course_id = c.id AND er.semester_id = :semester_id
                       AND er.status = 'REGISTERED') AS registered_count
            FROM courses c
            {_FACULTY_JOIN_SQL}
            WHERE c.elective_basket_id = ANY(:basket_ids)
            ORDER BY c.code
        """), {
            "basket_ids": [str(b) for b in basket_ids],
            "semester_id": str(semester_id),
        })).mappings().all()

        out: dict[str, list[dict]] = {str(b): [] for b in basket_ids}
        for r in rows:
            out[r["basket_id"]].append({k: v for k, v in r.items() if k != "basket_id"})
        return out

    # -----------------------------------------------------------------
    # Dean — assign faculty to each choice, for one running term.
    # -----------------------------------------------------------------

    @staticmethod
    async def list_slots_for_term(semester_id: UUID, dean_id: UUID, db: AsyncSession) -> list[dict]:
        """Every elective slot that applies to this running term, with each
        choice's faculty for that term. The term's semester number selects the
        slots; the term itself selects the assignments."""
        await assert_dean_owns_semester_program(
            dean_id, semester_id, db, "Semester not found in your governed programs.",
        )
        sem = (await db.execute(text("""
            SELECT sem.number, b.program_id AS acad_program_id
            FROM acad_semesters sem
            JOIN acad_batches b ON b.id = sem.batch_id
            WHERE sem.id = :sid
        """), {"sid": str(semester_id)})).mappings().first()
        if sem is None:
            raise AcadServiceError("SEMESTER_NOT_FOUND", "Semester not found.", 404)

        baskets = (await db.execute(text("""
            SELECT b.id, b.name, b.description, b.credits, b.semester, b.status
            FROM elective_baskets b
            JOIN programs p ON p.id = b.program_id
            WHERE p.acad_program_id = :apid
              AND p.status = 'PUBLISHED'
              AND b.semester = :num
            ORDER BY b.name
        """), {"apid": str(sem["acad_program_id"]), "num": sem["number"]})).mappings().all()
        if not baskets:
            return []

        options = await ElectiveService._options_for_baskets(
            [b["id"] for b in baskets], semester_id, db,
        )
        return [
            {
                "basket_id": b["id"], "name": b["name"], "description": b["description"],
                "credits": b["credits"], "semester": b["semester"], "status": b["status"],
                "semester_id": semester_id,
                "options": options.get(str(b["id"]), []),
            }
            for b in baskets
        ]

    @staticmethod
    async def assign_choice_faculty(
        course_id: UUID,
        semester_id: UUID,
        faculty_user_id: UUID,
        dean_id: UUID,
        db: AsyncSession,
        *,
        actor_role: str = "DEAN",
        tenant_id: UUID | None = None,
        schema_name: str | None = None,
    ) -> None:
        """Make `faculty_user_id` the PRIMARY faculty for this elective choice in
        this term. Idempotent; reassigning revokes the previous PRIMARY.

        Delegates to AssignmentService so dean scope, audit logging, notifications
        and faculty-role validation are the same ones ordinary subject assignment
        already enforces — an elective is not a special kind of subject.
        """
        await assert_dean_owns_semester_program(
            dean_id, semester_id, db, "Semester not found in your governed programs.",
        )
        in_slot = (await db.execute(text(
            "SELECT 1 FROM courses WHERE id = :cid AND elective_basket_id IS NOT NULL"
        ), {"cid": str(course_id)})).first()
        if in_slot is None:
            raise AcadServiceError(
                "NOT_AN_ELECTIVE_CHOICE", "That subject is not an elective choice.", 400,
            )

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
                return  # already assigned — nothing to do
            await AssignmentService.revoke(
                primary.id, revoked_by=dean_id, actor_role=actor_role,
                tenant_id=tenant_id, schema_name=schema_name, db=db,
            )

        try:
            await AssignmentService.create(
                AssignmentCreate(
                    course_id=course_id,
                    faculty_user_id=faculty_user_id,
                    semester_id=semester_id,
                    role_in_course=CourseRoleInCourse.PRIMARY,
                ),
                assigned_by=dean_id, actor_role=actor_role,
                tenant_id=tenant_id, schema_name=schema_name, db=db,
            )
        except AssignmentServiceError as e:
            raise AcadServiceError(e.code, e.message, e.status_code)

    # -----------------------------------------------------------------
    # Student — one choice per slot, while the slot is OPEN.
    # -----------------------------------------------------------------

    @staticmethod
    async def list_slots_for_student(student_id: UUID, db: AsyncSession) -> list[dict]:
        """The elective slots this student must satisfy: those defined at their
        current semester number on the PUBLISHED program their batch belongs to,
        and themselves at least PUBLISHED. Each carries its options and the
        student's own choice, so the UI needs no second round-trip."""
        term = await _get_student_term(student_id, db)
        if term is None:
            return []

        basket_rows = (await db.execute(text("""
            SELECT b.id, b.name, b.description, b.credits, b.semester, b.status
            FROM elective_baskets b
            JOIN programs p ON p.id = b.program_id
            WHERE p.acad_program_id = :acad_program_id
              AND p.status = 'PUBLISHED'
              AND b.semester = :semester_number
              AND b.status = ANY(:visible)
            ORDER BY b.name
        """), {
            "acad_program_id": str(term.acad_program_id),
            "semester_number": term.semester_number,
            "visible": list(_STUDENT_VISIBLE),
        })).mappings().all()
        if not basket_rows:
            return []

        options = await ElectiveService._options_for_baskets(
            [r["id"] for r in basket_rows], term.semester_id, db,
        )
        chosen = {
            str(r["basket_id"]): r["course_id"]
            for r in (await db.execute(text("""
                SELECT basket_id, course_id FROM elective_registrations
                WHERE student_user_id = :sid AND status = 'REGISTERED'
            """), {"sid": str(student_id)})).mappings().all()
        }

        return [
            {
                "basket_id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "credits": r["credits"],
                "semester": r["semester"],
                "semester_id": term.semester_id,
                "status": r["status"],
                # Only an OPEN slot accepts a choice, or a change of choice.
                "can_register": r["status"] == ElectiveSlotStatus.OPEN.value,
                "options": options.get(str(r["id"]), []),
                "chosen_course_id": chosen.get(str(r["id"])),
            }
            for r in basket_rows
        ]

    @staticmethod
    async def _assert_slot_registerable(
        basket_id: UUID, course_id: UUID, term: _StudentTerm, db: AsyncSession,
    ) -> None:
        slot = (await db.execute(text("""
            SELECT b.id, b.name, b.semester, b.status, p.status AS program_status,
                   p.acad_program_id
            FROM elective_baskets b
            JOIN programs p ON p.id = b.program_id
            WHERE b.id = :basket_id
        """), {"basket_id": str(basket_id)})).mappings().first()
        if slot is None:
            raise AcadServiceError("SLOT_NOT_FOUND", "Elective slot not found.", 404)
        if slot["program_status"] != "PUBLISHED":
            raise AcadServiceError(
                "PROGRAM_NOT_PUBLISHED",
                "This elective's program has not been published yet.", 400,
            )
        if slot["acad_program_id"] != term.acad_program_id:
            raise AcadServiceError(
                "SLOT_NOT_IN_PROGRAM", "This elective is not part of your program.", 403,
            )
        if slot["semester"] != term.semester_number:
            raise AcadServiceError(
                "SLOT_NOT_IN_CURRENT_SEMESTER",
                "This elective belongs to a different semester.", 400,
            )
        if slot["status"] != ElectiveSlotStatus.OPEN.value:
            not_yet = slot["status"] == ElectiveSlotStatus.PUBLISHED.value
            raise AcadServiceError(
                "SLOT_NOT_OPEN",
                f"Registration for {slot['name']} has not opened yet." if not_yet
                else f"Registration for {slot['name']} has closed.",
                409,
            )

        in_slot = (await db.execute(text(
            "SELECT 1 FROM courses WHERE id = :course_id AND elective_basket_id = :basket_id"
        ), {"course_id": str(course_id), "basket_id": str(basket_id)})).first()
        if in_slot is None:
            raise AcadServiceError(
                "COURSE_NOT_IN_SLOT", "That subject is not a choice in this elective slot.", 400,
            )

    @staticmethod
    async def register(
        basket_id: UUID, course_id: UUID, student_id: UUID, db: AsyncSession,
    ) -> ElectiveRegistration:
        """Choose `course_id` for slot `basket_id`. Re-registering while the slot
        is still OPEN replaces the previous choice; the unique (basket, student)
        constraint is what guarantees exactly one option per slot. Phase 5 has no
        seat cap, so there is no capacity check."""
        term = await _get_student_term(student_id, db)
        if term is None:
            raise AcadServiceError(
                "NO_ACTIVE_ENROLLMENT", "You are not enrolled in an active section.", 400,
            )
        await ElectiveService._assert_slot_registerable(basket_id, course_id, term, db)

        existing = (await db.execute(
            select(ElectiveRegistration).where(
                ElectiveRegistration.basket_id == basket_id,
                ElectiveRegistration.student_user_id == student_id,
            )
        )).scalar_one_or_none()

        if existing is not None:
            existing.course_id = course_id
            existing.semester_id = term.semester_id
            existing.status = ElectiveRegistrationStatus.REGISTERED.value
            existing.registered_at = datetime.utcnow()
            existing.updated_at = datetime.utcnow()
            reg = existing
        else:
            reg = ElectiveRegistration(
                id=uuid.uuid4(), basket_id=basket_id, course_id=course_id,
                semester_id=term.semester_id, student_user_id=student_id,
                status=ElectiveRegistrationStatus.REGISTERED.value,
            )
            db.add(reg)
        await db.commit()
        await db.refresh(reg)
        return reg

    @staticmethod
    async def drop(basket_id: UUID, student_id: UUID, db: AsyncSession) -> ElectiveRegistration:
        """Only while the slot is OPEN. Once CLOSED the roster is final — the
        faculty is already teaching and marking that class."""
        slot_status = (await db.execute(text(
            "SELECT status FROM elective_baskets WHERE id = :bid"
        ), {"bid": str(basket_id)})).scalar_one_or_none()
        if slot_status is None:
            raise AcadServiceError("SLOT_NOT_FOUND", "Elective slot not found.", 404)
        if slot_status != ElectiveSlotStatus.OPEN.value:
            raise AcadServiceError(
                "SLOT_NOT_OPEN", "Registration has closed; this choice can no longer be changed.", 409,
            )

        reg = (await db.execute(
            select(ElectiveRegistration).where(
                ElectiveRegistration.basket_id == basket_id,
                ElectiveRegistration.student_user_id == student_id,
            )
        )).scalar_one_or_none()
        if reg is None:
            raise AcadServiceError("REGISTRATION_NOT_FOUND", "No choice recorded for this elective.", 404)
        reg.status = ElectiveRegistrationStatus.DROPPED.value
        reg.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(reg)
        return reg

    @staticmethod
    async def get_my_registrations(student_id: UUID, db: AsyncSession) -> list[dict]:
        term = await _get_student_term(student_id, db)
        current_semester = term.semester_id if term else None
        rows = (await db.execute(text("""
            SELECT er.id, er.basket_id, er.semester_id, er.status, er.registered_at,
                   b.name AS basket_name,
                   c.id AS course_id, c.code AS course_code, c.title AS course_title, c.credits,
                   COALESCE(sem.label, CONCAT('Semester ', sem.number)) AS semester_label
            FROM elective_registrations er
            JOIN elective_baskets b   ON b.id   = er.basket_id
            JOIN courses c            ON c.id   = er.course_id
            JOIN acad_semesters sem   ON sem.id = er.semester_id
            WHERE er.student_user_id = :student_id
            ORDER BY er.registered_at DESC
        """), {"student_id": str(student_id)})).mappings().all()
        return [
            {**dict(r), "is_current": current_semester is not None and r["semester_id"] == current_semester}
            for r in rows
        ]

    # -----------------------------------------------------------------
    # Faculty — the combined elective class.
    #
    # Grouping is by course, never by section: MCA-A's 20 students and MCA-B's
    # 15 who both chose Artificial Intelligence surface as ONE class of 35.
    # A faculty member sees only the students who chose the course they teach,
    # never those of a sibling elective in the same slot.
    # -----------------------------------------------------------------

    @staticmethod
    async def get_faculty_elective_roster(faculty_id: UUID, db: AsyncSession) -> list[dict]:
        rows = (await db.execute(text("""
            SELECT
                c.id::text               AS course_id,
                c.code                   AS course_code,
                c.title                  AS course_title,
                er.basket_id::text       AS basket_id,
                er.semester_id::text     AS semester_id,
                COALESCE(sem.label, CONCAT('Semester ', sem.number)) AS semester_label,
                b.name                   AS basket_name,
                er.student_user_id::text AS student_id,
                u.full_name              AS student_name,
                sp.usn                   AS usn,
                u.email                  AS student_email,
                sec.name                 AS section_name,
                er.registered_at         AS registered_at
            FROM elective_registrations er
            JOIN elective_baskets b   ON b.id   = er.basket_id
            JOIN courses c            ON c.id   = er.course_id
            JOIN acad_semesters sem   ON sem.id = er.semester_id
            JOIN subject_assignments sa ON sa.course_id       = er.course_id
                                       AND sa.semester_id     = er.semester_id
                                       AND sa.faculty_user_id = :faculty_id
                                       AND sa.is_active       = true
                                       AND sa.role_in_course IN ('PRIMARY', 'CO_FACULTY')
            JOIN users u              ON u.id = er.student_user_id
            LEFT JOIN sis_student_profiles sp ON sp.user_id = er.student_user_id
            LEFT JOIN LATERAL (
                SELECT s.name
                FROM acad_enrollments ae
                JOIN acad_sections s ON s.id = ae.section_id
                WHERE ae.student_id = er.student_user_id AND ae.is_active = true
                LIMIT 1
            ) sec ON true
            WHERE er.status = 'REGISTERED'
            ORDER BY c.title, u.full_name
        """), {"faculty_id": str(faculty_id)})).mappings().all()

        by_course: dict[str, dict] = {}
        for r in rows:
            group = by_course.setdefault(r["course_id"], {
                "course_id": r["course_id"],
                "course_code": r["course_code"],
                "course_title": r["course_title"],
                "basket_id": r["basket_id"],
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
                "section_name": r["section_name"],
                "registered_at": r["registered_at"],
            })

        result = list(by_course.values())
        for g in result:
            g["total_students"] = len(g["students"])
            # The combined class spans however many sections chose this option.
            g["section_count"] = len({s["section_name"] for s in g["students"] if s["section_name"]})
        return result
