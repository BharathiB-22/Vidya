"""Subject Assignment — service layer (H-31).

Business rules:
  - Only DEAN or ADMIN may create/revoke assignments (enforced at router).
  - A faculty_user_id must be an active FACULTY-role user in the tenant.
  - At most one active PRIMARY assignment per (course_id, semester_id).
  - A user may not hold two active assignments for the same course+semester.
  - Revocation is soft-delete: is_active=False, revoked_at, revoked_by stamped.
  - Every mutation emits an AuditLog entry (non-blocking — swallowed on failure).
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("vidya.academics.assignment")

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.modules.m_academics.assignment_repository import SubjectAssignmentRepository
from app.modules.m_academics.dean_scope import get_dean_program_ids, get_semester_program_id
from app.modules.m_academics.assignment_schemas import (
    AssignmentCreate,
    AssignmentListResponse,
    AssignmentOut,
    CourseInfo,
    CourseWithAssignmentsOut,
    FacultyInfo,
    SectionInfo,
    SemesterInfo,
    ValidSemesterOut,
    ValidSemestersOut,
)
from app.modules.m_academics.models import CourseRoleInCourse, SubjectAssignment


class AssignmentServiceError(Exception):
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
            "notification_failed type=%s recipient=%s",
            notification_type,
            recipient_user_id,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _fetch_course(course_id: UUID, db: AsyncSession) -> CourseInfo:
    row = (
        await db.execute(
            text("SELECT id, code, title FROM courses WHERE id = :id"),
            {"id": str(course_id)},
        )
    ).mappings().one_or_none()
    if row is None:
        raise AssignmentServiceError("COURSE_NOT_FOUND", "Course not found.", 404)
    return CourseInfo(id=row["id"], code=row["code"], title=row["title"])


async def _fetch_section(section_id: UUID, db: AsyncSession) -> SectionInfo:
    row = (
        await db.execute(
            text("SELECT id, name FROM acad_sections WHERE id = :id"),
            {"id": str(section_id)},
        )
    ).mappings().one_or_none()
    if row is None:
        raise AssignmentServiceError("SECTION_NOT_FOUND", "Section not found.", 404)
    return SectionInfo(id=row["id"], name=row["name"])


async def _fetch_semester(semester_id: UUID, db: AsyncSession) -> SemesterInfo:
    row = (
        await db.execute(
            text("SELECT id, number, label FROM acad_semesters WHERE id = :id"),
            {"id": str(semester_id)},
        )
    ).mappings().one_or_none()
    if row is None:
        raise AssignmentServiceError("SEMESTER_NOT_FOUND", "Semester not found.", 404)
    return SemesterInfo(id=row["id"], number=row["number"], label=row["label"])


async def _check_program_alignment(
    course_id: UUID, semester_id: UUID, db: AsyncSession
) -> None:
    """Reject an assignment whose course and semester belong to different
    institutional programs.

    A course's own program (``courses.program_id`` -> curriculum ``programs``
    table) and a semester's program (``acad_semesters`` -> ``acad_batches`` ->
    ``acad_programs``) are two independently-editable hierarchies, bridged only
    by ``programs.acad_program_id``.  Nothing previously checked that a course
    being assigned and the semester it is being assigned into actually agree on
    which program they belong to, which let a course from one program (e.g.
    MCA) be paired with a semester from a completely unrelated program (e.g.
    BSc Chemistry) purely because both existed and both validated in isolation.

    Resolved entirely from existing foreign keys — no hardcoded program names
    or ids. If the course's curriculum program has no ``acad_program_id``
    bridge yet (nullable, tenant may not have linked it), alignment cannot be
    determined and the assignment is allowed through unchanged.
    """
    row = (
        await db.execute(
            text(
                "SELECT "
                "  course_prog.id   AS course_program_id, "
                "  course_prog.name AS course_program_name, "
                "  sem_prog.id      AS semester_program_id, "
                "  sem_prog.name    AS semester_program_name "
                "FROM   courses c "
                "JOIN   programs p              ON p.id  = c.program_id "
                "LEFT   JOIN acad_programs course_prog ON course_prog.id = p.acad_program_id "
                "CROSS  JOIN acad_semesters sem "
                "JOIN   acad_batches ab         ON ab.id = sem.batch_id "
                "JOIN   acad_programs sem_prog  ON sem_prog.id = ab.program_id "
                "WHERE  c.id = :course_id AND sem.id = :semester_id"
            ),
            {"course_id": str(course_id), "semester_id": str(semester_id)},
        )
    ).mappings().one_or_none()

    if row is None or row["course_program_id"] is None:
        # Course's program has no acad-program bridge yet — nothing to
        # validate against; do not invent a new blocking rule here.
        return

    if row["course_program_id"] != row["semester_program_id"]:
        raise AssignmentServiceError(
            "PROGRAM_MISMATCH",
            (
                f"This course belongs to '{row['course_program_name']}', but the "
                f"selected semester belongs to '{row['semester_program_name']}'. "
                "Choose a semester that belongs to the course's own program."
            ),
        )


async def _fetch_faculty(user_id: UUID, db: AsyncSession) -> FacultyInfo:
    row = (
        await db.execute(
            text(
                "SELECT id, full_name, email, role, is_active "
                "FROM users WHERE id = :id"
            ),
            {"id": str(user_id)},
        )
    ).mappings().one_or_none()
    if row is None:
        raise AssignmentServiceError("USER_NOT_FOUND", "Faculty user not found.", 404)
    if not row["is_active"]:
        raise AssignmentServiceError("USER_INACTIVE", "Faculty user is inactive.")
    if row["role"] not in ("FACULTY", "DEAN"):
        raise AssignmentServiceError(
            "INVALID_ROLE",
            f"User role is '{row['role']}'; only FACULTY users (and DEANs with FACULTY responsibility) may be assigned to courses.",
        )
    if row["role"] == "DEAN":
        grant = (
            await db.execute(
                text(
                    "SELECT 1 FROM faculty_role_grants "
                    "WHERE faculty_user_id = :uid AND role_code = 'FACULTY' AND is_active = true "
                    "LIMIT 1"
                ),
                {"uid": str(user_id)},
            )
        ).one_or_none()
        if grant is None:
            raise AssignmentServiceError(
                "INVALID_ROLE",
                "This DEAN does not hold an active FACULTY responsibility. "
                "Grant FACULTY responsibility before assigning courses.",
            )
    return FacultyInfo(id=row["id"], full_name=row["full_name"], email=row["email"])


async def _enrich(
    assignments: list[SubjectAssignment],
    db: AsyncSession,
) -> list[AssignmentOut]:
    """Bulk-fetch course, semester, section, and faculty info for a list of assignments."""
    if not assignments:
        return []

    course_ids   = list({str(a.course_id)      for a in assignments})
    semester_ids = list({str(a.semester_id)     for a in assignments})
    section_ids  = list({str(a.section_id)      for a in assignments if a.section_id})
    faculty_ids  = list({str(a.faculty_user_id) for a in assignments})

    courses_rows = (
        await db.execute(
            text("SELECT id::text, code, title FROM courses WHERE id = ANY(:ids)"),
            {"ids": course_ids},
        )
    ).mappings().all()

    semester_rows = (
        await db.execute(
            text("SELECT id::text, number, label FROM acad_semesters WHERE id = ANY(:ids)"),
            {"ids": semester_ids},
        )
    ).mappings().all()

    section_rows = (
        await db.execute(
            text("SELECT id::text, name FROM acad_sections WHERE id = ANY(:ids)"),
            {"ids": section_ids},
        )
    ).mappings().all() if section_ids else []

    faculty_rows = (
        await db.execute(
            text("SELECT id::text, full_name, email FROM users WHERE id = ANY(:ids)"),
            {"ids": faculty_ids},
        )
    ).mappings().all()

    courses_map  = {r["id"]: r for r in courses_rows}
    semester_map = {r["id"]: r for r in semester_rows}
    section_map  = {r["id"]: r for r in section_rows}
    faculty_map  = {r["id"]: r for r in faculty_rows}

    out = []
    for a in assignments:
        c_row = courses_map.get(str(a.course_id))
        s_row = semester_map.get(str(a.semester_id))
        sec_row = section_map.get(str(a.section_id)) if a.section_id else None
        f_row = faculty_map.get(str(a.faculty_user_id))
        out.append(
            AssignmentOut(
                id=a.id,
                course_id=a.course_id,
                faculty_user_id=a.faculty_user_id,
                semester_id=a.semester_id,
                section_id=a.section_id,
                assigned_by_user_id=a.assigned_by_user_id,
                assigned_at=a.assigned_at,
                is_active=a.is_active,
                role_in_course=a.role_in_course,
                revoked_at=a.revoked_at,
                revoked_by_user_id=a.revoked_by_user_id,
                course=CourseInfo(
                    id=c_row["id"], code=c_row["code"], title=c_row["title"]
                ) if c_row else None,
                semester=SemesterInfo(
                    id=s_row["id"], number=s_row["number"], label=s_row["label"]
                ) if s_row else None,
                section=SectionInfo(
                    id=sec_row["id"], name=sec_row["name"]
                ) if sec_row else None,
                faculty=FacultyInfo(
                    id=f_row["id"], full_name=f_row["full_name"], email=f_row["email"]
                ) if f_row else None,
            )
        )
    return out


# ---------------------------------------------------------------------------
# AssignmentService
# ---------------------------------------------------------------------------

class AssignmentService:

    @staticmethod
    async def list_valid_semesters(course_id: UUID, db: AsyncSession) -> ValidSemestersOut:
        """Semesters a course may legitimately be assigned into.

        Scoped strictly to the course's own institutional program (course ->
        curriculum program -> acad_program_id -> acad_batches -> acad_semesters)
        so the Assign Faculty dialog can offer only semesters that actually
        belong to this course's program — structurally preventing the mistake
        that _check_program_alignment only used to catch after the fact.

        If the course's curriculum program has no acad_program_id bridge yet,
        scoping is impossible; every active semester is returned instead
        (``scoped=False``), matching _check_program_alignment's own permissive
        policy for that same edge case so the picker and the guard never
        disagree.
        """
        course_row = (
            await db.execute(
                text(
                    "SELECT c.id, p.acad_program_id, ap.name AS program_name "
                    "FROM   courses c "
                    "JOIN   programs p ON p.id = c.program_id "
                    "LEFT   JOIN acad_programs ap ON ap.id = p.acad_program_id "
                    "WHERE  c.id = :id"
                ),
                {"id": str(course_id)},
            )
        ).mappings().one_or_none()
        if course_row is None:
            raise AssignmentServiceError("COURSE_NOT_FOUND", "Course not found.", 404)

        acad_program_id = course_row["acad_program_id"]

        sem_query = (
            "SELECT sem.id, sem.number, sem.label, "
            "       ab.id AS batch_id, ab.name AS batch_name, "
            "       ap.id AS program_id, ap.name AS program_name, ap.code AS program_code "
            "FROM   acad_semesters sem "
            "JOIN   acad_batches ab  ON ab.id = sem.batch_id "
            "JOIN   acad_programs ap ON ap.id = ab.program_id "
            "WHERE  sem.is_active = true AND ab.is_active = true "
        )

        if acad_program_id is None:
            rows = (
                await db.execute(
                    text(sem_query + "ORDER BY ap.name, ab.start_year DESC, sem.number")
                )
            ).mappings().all()
            return ValidSemestersOut(
                course_id=course_id,
                program_id=None,
                program_name=None,
                scoped=False,
                items=[ValidSemesterOut(**r) for r in rows],
            )

        rows = (
            await db.execute(
                text(sem_query + "AND ap.id = :pid ORDER BY ab.start_year DESC, sem.number"),
                {"pid": str(acad_program_id)},
            )
        ).mappings().all()

        return ValidSemestersOut(
            course_id=course_id,
            program_id=acad_program_id,
            program_name=course_row["program_name"],
            scoped=True,
            items=[ValidSemesterOut(**r) for r in rows],
        )

    @staticmethod
    async def create(
        body: AssignmentCreate,
        *,
        assigned_by: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> AssignmentOut:
        # Validate referential integrity + user role
        course   = await _fetch_course(body.course_id, db)
        semester = await _fetch_semester(body.semester_id, db)
        section  = await _fetch_section(body.section_id, db) if body.section_id else None
        faculty  = await _fetch_faculty(body.faculty_user_id, db)

        # Structural guard: the course and the semester must belong to the same
        # institutional program. See _check_program_alignment for why this is
        # necessary — course/semester existence alone does not guarantee they
        # belong together.
        await _check_program_alignment(body.course_id, body.semester_id, db)

        # Dean scope enforcement: DEAN may only assign to courses in programs they govern.
        # ADMIN and SUPER_ADMIN bypass this check.
        if actor_role == "DEAN":
            acad_program_id = (
                await db.execute(
                    text(
                        "SELECT p.acad_program_id FROM programs p "
                        "JOIN courses c ON c.program_id = p.id "
                        "WHERE c.id = :cid LIMIT 1"
                    ),
                    {"cid": str(body.course_id)},
                )
            ).scalar_one_or_none()
            governed = await get_dean_program_ids(assigned_by, actor_role, db)
            if (
                governed is not None
                and (acad_program_id is None or acad_program_id not in governed)
            ):
                raise AssignmentServiceError(
                    "PROGRAM_NOT_IN_SCOPE",
                    "You may only assign faculty to courses within programs you govern.",
                    403,
                )

        # Duplicate check: same faculty already active on this course+semester
        dup = await SubjectAssignmentRepository.find_duplicate(
            body.course_id, body.faculty_user_id, body.semester_id, db=db
        )
        if dup is not None:
            raise AssignmentServiceError(
                "DUPLICATE_ASSIGNMENT",
                "This faculty member already has an active assignment for this course and semester.",
            )

        # One active PRIMARY allowed per course+semester
        if body.role_in_course == CourseRoleInCourse.PRIMARY:
            count = await SubjectAssignmentRepository.count_active_primary(
                body.course_id, body.semester_id, db=db
            )
            if count > 0:
                raise AssignmentServiceError(
                    "PRIMARY_ALREADY_EXISTS",
                    "A PRIMARY faculty is already assigned to this course for the given semester. "
                    "Revoke the existing PRIMARY assignment before creating a new one.",
                )

        row = await SubjectAssignmentRepository.create(
            course_id=body.course_id,
            faculty_user_id=body.faculty_user_id,
            semester_id=body.semester_id,
            section_id=body.section_id,
            role_in_course=body.role_in_course,
            assigned_by_user_id=assigned_by,
            db=db,
        )
        await db.commit()

        await AuditService.log(
            AuditEventType.SUBJECT_ASSIGNMENT_CREATED,
            actor_user_id=assigned_by,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SubjectAssignment",
            target_id=str(row.id),
            metadata={
                "course_id":      str(body.course_id),
                "course_code":    course.code,
                "faculty_user_id": str(body.faculty_user_id),
                "semester_id":    str(body.semester_id),
                "role_in_course": body.role_in_course.value,
            },
        )

        from app.core.notifications.models import NotificationType
        await _notify_safe(
            notification_type=NotificationType.COURSE_ASSIGNED,
            recipient_user_id=faculty.id,
            recipient_email=faculty.email,
            title="Course Assignment",
            body=f"You have been assigned to course \"{course.code} – {course.title}\" as {body.role_in_course.value}.",
            entity_type="SubjectAssignment",
            entity_id=str(row.id),
            db=db,
        )

        return AssignmentOut(
            id=row.id,
            course_id=row.course_id,
            faculty_user_id=row.faculty_user_id,
            semester_id=row.semester_id,
            section_id=row.section_id,
            assigned_by_user_id=row.assigned_by_user_id,
            assigned_at=row.assigned_at,
            is_active=row.is_active,
            role_in_course=row.role_in_course,
            revoked_at=row.revoked_at,
            revoked_by_user_id=row.revoked_by_user_id,
            course=course,
            semester=semester,
            section=section,
            faculty=faculty,
        )

    @staticmethod
    async def revoke(
        assignment_id: UUID,
        *,
        revoked_by: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> AssignmentOut:
        row = await SubjectAssignmentRepository.get_by_id(assignment_id, db=db)
        if row is None:
            raise AssignmentServiceError("NOT_FOUND", "Assignment not found.", 404)
        if not row.is_active:
            raise AssignmentServiceError(
                "ALREADY_REVOKED", "Assignment is already revoked."
            )

        revoked = await SubjectAssignmentRepository.revoke(
            assignment_id, revoked_by, db=db
        )
        await db.commit()

        await AuditService.log(
            AuditEventType.SUBJECT_ASSIGNMENT_REVOKED,
            actor_user_id=revoked_by,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SubjectAssignment",
            target_id=str(assignment_id),
            metadata={
                "course_id":      str(row.course_id),
                "faculty_user_id": str(row.faculty_user_id),
                "semester_id":    str(row.semester_id),
                "role_in_course": row.role_in_course.value if row.role_in_course else None,
            },
        )

        rows = await _enrich([revoked], db)
        enriched = rows[0]

        from app.core.notifications.models import NotificationType
        course_label = (
            f"{enriched.course.code} – {enriched.course.title}"
            if enriched.course else str(row.course_id)
        )
        faculty_email = enriched.faculty.email if enriched.faculty else None
        await _notify_safe(
            notification_type=NotificationType.COURSE_ASSIGNMENT_REVOKED,
            recipient_user_id=row.faculty_user_id,
            recipient_email=faculty_email,
            title="Course Assignment Removed",
            body=f"Your assignment for course \"{course_label}\" has been removed.",
            entity_type="SubjectAssignment",
            entity_id=str(assignment_id),
            db=db,
        )

        return enriched

    @staticmethod
    async def _governed_course_ids(governed: list[UUID], db: AsyncSession) -> list[UUID]:
        from app.modules.m01_program_advisor.models import Course, Program

        result = await db.execute(
            select(Course.id)
            .join(Program, Program.id == Course.program_id)
            .where(Program.acad_program_id.in_(governed))
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_all(
        *,
        semester_id: UUID | None = None,
        section_id: UUID | None = None,
        include_inactive: bool = False,
        caller_role: str | None = None,
        caller_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> AssignmentListResponse:
        """List all assignments in the tenant (no course filter). DEAN/ADMIN only."""
        course_ids: list[UUID] | None = None
        if caller_role == "DEAN" and caller_user_id is not None:
            governed = await get_dean_program_ids(caller_user_id, caller_role, db)
            if governed is not None:
                course_ids = await AssignmentService._governed_course_ids(governed, db)

        rows = await SubjectAssignmentRepository.list_all(
            semester_id=semester_id,
            section_id=section_id,
            include_inactive=include_inactive,
            course_ids=course_ids,
            db=db,
        )
        items = await _enrich(rows, db)
        return AssignmentListResponse(total=len(items), items=items)

    @staticmethod
    async def list_courses_with_assignments(
        semester_id: UUID,
        *,
        section_id: UUID | None = None,
        db: AsyncSession,
    ) -> list[CourseWithAssignmentsOut]:
        """Every course belonging to this operational semester's program,
        each with its (possibly empty) list of active assignments.

        Unlike `list_all`, which only returns rows that already exist in
        `subject_assignments`, this starts from the course catalog so a
        course with zero faculty assigned still appears -- needed by the
        Timetable slot picker, which must let the Dean save a slot with no
        faculty when none are assigned yet, instead of hiding the course.
        """
        acad_program_id = await get_semester_program_id(semester_id, db)
        if acad_program_id is None:
            return []

        sem_row = (await db.execute(
            text("SELECT number FROM acad_semesters WHERE id = :id"),
            {"id": str(semester_id)},
        )).mappings().first()
        if sem_row is None:
            return []

        course_rows = (await db.execute(
            text(
                "SELECT c.id, c.code, c.title "
                "FROM courses c "
                "JOIN programs p ON p.id = c.program_id "
                "WHERE p.acad_program_id = :acad_program_id "
                "  AND p.status IN ('APPROVED', 'PUBLISHED') "
                "  AND c.semester = :semester_number "
                "ORDER BY c.title"
            ),
            {"acad_program_id": str(acad_program_id), "semester_number": sem_row["number"]},
        )).mappings().all()
        if not course_rows:
            return []

        course_ids = [row["id"] for row in course_rows]
        rows = await SubjectAssignmentRepository.list_all(
            semester_id=semester_id, section_id=section_id,
            include_inactive=False, course_ids=course_ids, db=db,
        )
        enriched = await _enrich(rows, db)
        by_course: dict[UUID, list[AssignmentOut]] = {}
        for a in enriched:
            by_course.setdefault(a.course_id, []).append(a)

        return [
            CourseWithAssignmentsOut(
                course_id=row["id"], code=row["code"], title=row["title"],
                assignments=by_course.get(row["id"], []),
            )
            for row in course_rows
        ]

    @staticmethod
    async def list_by_course(
        course_id: UUID,
        *,
        semester_id: UUID | None = None,
        section_id: UUID | None = None,
        include_inactive: bool = False,
        caller_role: str | None = None,
        caller_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> AssignmentListResponse:
        if caller_role == "DEAN" and caller_user_id is not None:
            governed = await get_dean_program_ids(caller_user_id, caller_role, db)
            if governed is not None:
                governed_course_ids = await AssignmentService._governed_course_ids(governed, db)
                if course_id not in governed_course_ids:
                    raise AssignmentServiceError(
                        "PROGRAM_NOT_IN_SCOPE",
                        "You may only view assignments for courses within programs you govern.",
                        403,
                    )

        rows = await SubjectAssignmentRepository.list_by_course(
            course_id, semester_id=semester_id, section_id=section_id,
            include_inactive=include_inactive, db=db
        )
        items = await _enrich(rows, db)
        return AssignmentListResponse(total=len(items), items=items)

    @staticmethod
    async def list_faculty_users(
        *,
        caller_role: str | None = None,
        caller_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> list[dict]:
        """Return all active users who may be assigned to courses.

        Includes FACULTY primary-role users plus DEAN users who hold an active
        FACULTY responsibility grant (DEAN+FACULTY dual-role accounts).

        For a DEAN caller, scoped by DEPARTMENT (not program): a dean governs
        exactly one department and may assign ANY faculty in that department,
        regardless of which program that faculty currently teaches. The dean's
        department(s) are resolved from their governed programs; a faculty
        member is "in" that department if it is their home department
        (sis_faculty_profiles.primary_department_id) OR they hold an active
        coordinator tie to a program in it — mirroring
        directory_repository._faculty_in_department.
        """
        scope_clause = ""
        params: dict = {}
        if caller_role == "DEAN" and caller_user_id is not None:
            dept_rows = (
                await db.execute(
                    text(
                        "SELECT DISTINCT ap.department_id "
                        "FROM   dean_program_assignments dpa "
                        "JOIN   acad_programs ap ON ap.id = dpa.program_id "
                        "WHERE  dpa.dean_user_id = :uid AND dpa.is_active = true "
                        "  AND  ap.department_id IS NOT NULL"
                    ),
                    {"uid": str(caller_user_id)},
                )
            ).all()
            dept_ids = [str(r[0]) for r in dept_rows]
            if not dept_ids:
                # Dean governs no department → sees no assignable faculty.
                # Never fall back to "everyone".
                return []
            scope_clause = (
                "  AND id IN ("
                # Home department (belongs to the dept even with no assignments yet)
                "    SELECT user_id FROM sis_faculty_profiles "
                "    WHERE primary_department_id = ANY(:dept_ids) "
                "    UNION "
                # Active coordinator tie to a program in the dept
                "    SELECT fpa.faculty_user_id FROM faculty_program_assignments fpa "
                "    JOIN acad_programs ap ON ap.id = fpa.program_id "
                "    WHERE fpa.is_active = true AND ap.department_id = ANY(:dept_ids) "
                "    UNION "
                # Active teaching tie to a course whose program is in the dept
                "    SELECT sa.faculty_user_id FROM subject_assignments sa "
                "    JOIN courses c ON c.id = sa.course_id "
                "    JOIN programs p ON p.id = c.program_id "
                "    JOIN acad_programs ap2 ON ap2.id = p.acad_program_id "
                "    WHERE sa.is_active = true AND ap2.department_id = ANY(:dept_ids) "
                "  ) "
            )
            params["dept_ids"] = dept_ids

        rows = (
            await db.execute(
                text(
                    "SELECT id::text, full_name, email, role "
                    "FROM users "
                    "WHERE is_active = true "
                    "  AND ("
                    "    role = 'FACULTY'"
                    "    OR ("
                    "      role = 'DEAN'"
                    "      AND id IN ("
                    "        SELECT faculty_user_id FROM faculty_role_grants"
                    "        WHERE role_code = 'FACULTY' AND is_active = true"
                    "      )"
                    "    )"
                    "  ) "
                    f"{scope_clause}"
                    "ORDER BY full_name"
                ),
                params,
            )
        ).mappings().all()
        return [
            {"id": r["id"], "full_name": r["full_name"], "email": r["email"], "role": r["role"]}
            for r in rows
        ]

    @staticmethod
    async def list_my_courses(
        faculty_user_id: UUID,
        *,
        include_inactive: bool = False,
        db: AsyncSession,
    ) -> AssignmentListResponse:
        rows = await SubjectAssignmentRepository.list_by_faculty(
            faculty_user_id, include_inactive=include_inactive, db=db
        )
        items = await _enrich(rows, db)
        return AssignmentListResponse(total=len(items), items=items)
