"""Academic Ownership & Responsibility — service layer (Phase B).

Business rules:
  - Admin and SUPER_ADMIN may assign faculty to any program in the tenant.
  - A DEAN may only assign/remove faculty from programs in their
    dean_program_assignments scope.
  - Faculty can belong to multiple departments (one row per program).
  - is_primary: at most one PRIMARY coordinator per program is enforced by
    a partial unique index; the service enforces it explicitly.
  - Soft-revoke only — rows are never deleted.
  - All mutations are audit-logged.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("vidya.academics.ownership")

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.notifications.dispatch import notify_user
from app.core.notifications.models import NotificationType
from app.modules.m_academics.ownership_schemas import (
    DashboardFacultyWorkload,
    DeanProgramOut,
    DeptInfo,
    FacultyAcademicResponsibilities,
    FacultyAcademicSummary,
    FacultyCourseEntry,
    FacultyProgramAssignCreate,
    FacultyProgramAssignOut,
    FacultyResponsibilityProgram,
    FacultyWorkloadItem,
    FacultyWorkloadResponse,
    MatrixCourse,
    MatrixDepartment,
    MatrixFaculty,
    MatrixProgram,
    MatrixSection,
    MatrixSemester,
    OwnershipDashboardSummary,
    OwnershipMatrixOut,
)


class OwnershipServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code       = code
        self.message    = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _require_dean_scope(dean_user_id: UUID, program_id: UUID, db: AsyncSession) -> None:
    """Raise 403 if dean_user_id does not govern program_id."""
    row = (
        await db.execute(
            text(
                "SELECT 1 FROM dean_program_assignments "
                "WHERE dean_user_id = :uid AND program_id = :pid AND is_active = true "
                "LIMIT 1"
            ),
            {"uid": str(dean_user_id), "pid": str(program_id)},
        )
    ).one_or_none()
    if row is None:
        raise OwnershipServiceError(
            "PROGRAM_NOT_IN_SCOPE",
            "You may only manage faculty for programs you govern.",
            403,
        )


async def _fetch_program_with_dept(program_id: UUID, db: AsyncSession) -> dict:
    row = (
        await db.execute(
            text(
                "SELECT ap.id, ap.name, ap.code, ap.degree_type, "
                "       ap.department_id, ap.is_active, "
                "       d.name AS dept_name, d.code AS dept_code "
                "FROM   acad_programs ap "
                "LEFT   JOIN acad_departments d ON d.id = ap.department_id "
                "WHERE  ap.id = :id"
            ),
            {"id": str(program_id)},
        )
    ).mappings().one_or_none()
    if row is None:
        raise OwnershipServiceError("PROGRAM_NOT_FOUND", "Program not found.", 404)
    if not row["is_active"]:
        raise OwnershipServiceError("PROGRAM_INACTIVE", "Program is not active.")
    return row


async def _fetch_faculty_user(user_id: UUID, db: AsyncSession) -> dict:
    row = (
        await db.execute(
            text(
                "SELECT id, full_name, email, role, is_active "
                "FROM   users WHERE id = :id"
            ),
            {"id": str(user_id)},
        )
    ).mappings().one_or_none()
    if row is None:
        raise OwnershipServiceError("USER_NOT_FOUND", "User not found.", 404)
    if not row["is_active"]:
        raise OwnershipServiceError("USER_INACTIVE", "User account is inactive.")
    if row["role"] not in ("FACULTY", "DEAN"):
        raise OwnershipServiceError(
            "INVALID_ROLE",
            f"Only FACULTY (or DEAN-with-FACULTY grant) may be assigned to programs; "
            f"this user has role '{row['role']}'.",
        )
    return row


# ---------------------------------------------------------------------------
# OwnershipService
# ---------------------------------------------------------------------------

class OwnershipService:

    # ------------------------------------------------------------------
    # Faculty responsibilities
    # ------------------------------------------------------------------

    @staticmethod
    async def get_faculty_responsibilities(
        faculty_user_id: UUID, *, db: AsyncSession
    ) -> FacultyAcademicResponsibilities:
        """Aggregated academic scope for a faculty member."""
        # Faculty identity: base login role + home department. The home
        # department is the faculty's OWN department (primary_department_id),
        # resolved independently of any program/course scope so it is never
        # masked by a stale program→department pairing.
        identity = (
            await db.execute(
                text(
                    "SELECT u.role, "
                    "       d.id AS dept_id, d.name AS dept_name, d.code AS dept_code "
                    "FROM   users u "
                    "LEFT   JOIN sis_faculty_profiles p ON p.user_id = u.id "
                    "LEFT   JOIN acad_departments     d ON d.id = p.primary_department_id "
                    "WHERE  u.id = :uid"
                ),
                {"uid": str(faculty_user_id)},
            )
        ).mappings().one_or_none()

        home_department = (
            DeptInfo(id=identity["dept_id"], name=identity["dept_name"], code=identity["dept_code"])
            if identity and identity["dept_id"] else None
        )

        # Active responsibility grants (GUIDE / EVALUATOR / BOARD, and sometimes
        # FACULTY itself — e.g. a DEAN explicitly granted FACULTY to unlock the
        # teaching workspace, per faculty_role_grants.role_code) plus the base
        # login role (FACULTY or DEAN) placed first. The base role is only
        # appended if a grant with that exact code doesn't already cover it —
        # a DEAN holding an explicit FACULTY grant must render as
        # ["DEAN", "FACULTY"], never ["FACULTY", "DEAN", "FACULTY"].
        grant_rows = (
            await db.execute(
                text(
                    "SELECT role_code FROM faculty_role_grants "
                    "WHERE faculty_user_id = :uid AND is_active = true"
                ),
                {"uid": str(faculty_user_id)},
            )
        ).fetchall()
        grants = sorted({r[0] for r in grant_rows})
        base_role = identity["role"] if identity else None
        responsibilities: list[str] = []
        if base_role in ("FACULTY", "DEAN"):
            responsibilities.append(base_role)
        responsibilities.extend(g for g in grants if g not in responsibilities)

        # Program-scope assignments. Department is resolved from the program's
        # OWN live department (ap.department_id) — never the stamped, possibly
        # stale fpa.department_id — so a program that has since moved departments
        # never renders under the wrong one.
        assign_rows = (
            await db.execute(
                text(
                    "SELECT fpa.id, fpa.program_id, fpa.department_id, fpa.is_primary, "
                    "       fpa.assigned_by, fpa.assigned_at, "
                    "       ap.name AS program_name, ap.code AS program_code, "
                    "       ap.degree_type, "
                    "       d.id   AS dept_id,   d.name AS dept_name, d.code AS dept_code, "
                    "       u.full_name AS assigned_by_name "
                    "FROM   faculty_program_assignments fpa "
                    "JOIN   acad_programs    ap ON ap.id = fpa.program_id "
                    "LEFT   JOIN acad_departments d ON d.id = ap.department_id "
                    "LEFT   JOIN users         u  ON u.id  = fpa.assigned_by "
                    "WHERE  fpa.faculty_user_id = :uid "
                    "  AND  fpa.is_active = true "
                    "ORDER  BY fpa.assigned_at"
                ),
                {"uid": str(faculty_user_id)},
            )
        ).mappings().all()

        # Deduplicate departments
        depts_seen: dict[str, DeptInfo] = {}
        programs: list[FacultyResponsibilityProgram] = []
        programs_seen: set[str] = set()
        for r in assign_rows:
            if r["dept_id"] and str(r["dept_id"]) not in depts_seen:
                depts_seen[str(r["dept_id"])] = DeptInfo(
                    id=r["dept_id"], name=r["dept_name"], code=r["dept_code"]
                )
            dept = depts_seen.get(str(r["dept_id"])) if r["dept_id"] else None
            programs_seen.add(str(r["program_id"]))
            programs.append(
                FacultyResponsibilityProgram(
                    id=r["program_id"],
                    name=r["program_name"],
                    code=r["program_code"],
                    degree_type=r["degree_type"],
                    department=dept,
                    is_primary=r["is_primary"],
                    assigned_by_name=r["assigned_by_name"],
                    assigned_at=r["assigned_at"],
                    source="APPOINTED",
                )
            )

        # Programs/departments implied by actual course-teaching assignments.
        #
        # Authoritative source: the COURSE's own program
        # (courses.program_id -> programs.acad_program_id -> acad_programs),
        # never the semester's scheduling chain (acad_semesters -> acad_batches
        # -> acad_programs). A subject_assignment's semester_id says WHEN a
        # course is taught; it does not redefine WHICH program the course
        # belongs to. Trusting the semester chain as ownership let a course
        # keep its own correct program while a data-entry mistake on its
        # semester_id (pointing into an unrelated program's batch) silently
        # overrode the displayed program/department with the wrong one.
        #
        # The semester chain is used only as a fallback, for courses whose
        # curriculum program has no acad_program_id bridge yet (tenants that
        # have not linked their curriculum to the ERP academic structure) —
        # for those, resolution keeps prior behavior unchanged rather than
        # returning nothing.
        implied_rows = (
            await db.execute(
                text(
                    "SELECT resolved.program_id, resolved.program_name, "
                    "       resolved.program_code, resolved.degree_type, "
                    "       resolved.dept_id, resolved.dept_name, resolved.dept_code, "
                    "       MIN(resolved.assigned_at) AS earliest_assigned_at "
                    "FROM ( "
                    "  SELECT sa.assigned_at, "
                    "         COALESCE(course_ap.id, sem_ap.id)     AS program_id, "
                    "         COALESCE(course_ap.name, sem_ap.name) AS program_name, "
                    "         COALESCE(course_ap.code, sem_ap.code) AS program_code, "
                    "         COALESCE(course_ap.degree_type, sem_ap.degree_type) AS degree_type, "
                    "         COALESCE(course_d.id, sem_d.id)     AS dept_id, "
                    "         COALESCE(course_d.name, sem_d.name) AS dept_name, "
                    "         COALESCE(course_d.code, sem_d.code) AS dept_code "
                    "  FROM   subject_assignments sa "
                    "  JOIN   courses c  ON c.id = sa.course_id "
                    "  LEFT   JOIN programs cp               ON cp.id = c.program_id "
                    "  LEFT   JOIN acad_programs course_ap    ON course_ap.id = cp.acad_program_id "
                    "  LEFT   JOIN acad_departments course_d  ON course_d.id = course_ap.department_id "
                    "  JOIN   acad_semesters sem ON sem.id = sa.semester_id "
                    "  LEFT   JOIN acad_batches   ab     ON ab.id = sem.batch_id "
                    "  LEFT   JOIN acad_programs  sem_ap ON sem_ap.id = ab.program_id "
                    "  LEFT   JOIN acad_departments sem_d ON sem_d.id = sem_ap.department_id "
                    "  WHERE  sa.faculty_user_id = :uid AND sa.is_active = true "
                    ") resolved "
                    "WHERE  resolved.program_id IS NOT NULL "
                    "GROUP  BY resolved.program_id, resolved.program_name, resolved.program_code, "
                    "          resolved.degree_type, resolved.dept_id, resolved.dept_name, resolved.dept_code "
                    "ORDER  BY resolved.program_name"
                ),
                {"uid": str(faculty_user_id)},
            )
        ).mappings().all()

        for r in implied_rows:
            if r["dept_id"] and str(r["dept_id"]) not in depts_seen:
                depts_seen[str(r["dept_id"])] = DeptInfo(
                    id=r["dept_id"], name=r["dept_name"], code=r["dept_code"]
                )
            if str(r["program_id"]) in programs_seen:
                continue
            programs_seen.add(str(r["program_id"]))
            dept = depts_seen.get(str(r["dept_id"])) if r["dept_id"] else None
            programs.append(
                FacultyResponsibilityProgram(
                    id=r["program_id"],
                    name=r["program_name"],
                    code=r["program_code"],
                    degree_type=r["degree_type"],
                    department=dept,
                    is_primary=False,
                    assigned_by_name=None,
                    assigned_at=r["earliest_assigned_at"],
                    source="TEACHING",
                )
            )

        # Course-level assignments from subject_assignments.
        #
        # Program/department are resolved from the COURSE's own program
        # (courses.program_id -> programs.acad_program_id -> acad_programs),
        # exactly as in `implied_rows` above — never from the semester's
        # scheduling chain. Semester number/label and section name are still
        # read directly off the actual subject_assignment row (that is a
        # correct use of the FK: it says WHEN/WHERE this teaching happens),
        # but they no longer double as the source of WHICH program/department
        # owns the course. The semester/batch chain remains only as a fallback
        # for courses whose curriculum program has no acad_program_id bridge.
        course_rows = (
            await db.execute(
                text(
                    "SELECT sa.id AS assignment_id, sa.course_id, sa.role_in_course, "
                    "       sa.is_active, "
                    "       c.code AS course_code, c.title AS course_title, "
                    "       sem.number AS sem_number, sem.label AS sem_label, "
                    "       sec.name AS section_name, "
                    "       COALESCE(course_ap.id, sem_ap.id)     AS program_id, "
                    "       COALESCE(course_ap.name, sem_ap.name) AS program_name, "
                    "       COALESCE(course_ap.code, sem_ap.code) AS program_code, "
                    "       COALESCE(course_d.id, sem_d.id)     AS department_id, "
                    "       COALESCE(course_d.name, sem_d.name) AS department_name "
                    "FROM   subject_assignments sa "
                    "JOIN   courses       c   ON c.id   = sa.course_id "
                    "JOIN   acad_semesters sem ON sem.id = sa.semester_id "
                    "LEFT   JOIN acad_sections sec ON sec.id = sa.section_id "
                    "LEFT   JOIN programs cp               ON cp.id = c.program_id "
                    "LEFT   JOIN acad_programs course_ap    ON course_ap.id = cp.acad_program_id "
                    "LEFT   JOIN acad_departments course_d  ON course_d.id = course_ap.department_id "
                    "LEFT   JOIN acad_batches   ab      ON ab.id  = sem.batch_id "
                    "LEFT   JOIN acad_programs  sem_ap  ON sem_ap.id = ab.program_id "
                    "LEFT   JOIN acad_departments sem_d ON sem_d.id = sem_ap.department_id "
                    "WHERE  sa.faculty_user_id = :uid "
                    "ORDER  BY COALESCE(course_ap.name, sem_ap.name), sem.number, c.code"
                ),
                {"uid": str(faculty_user_id)},
            )
        ).mappings().all()

        course_entries = [
            FacultyCourseEntry(
                assignment_id=r["assignment_id"],
                course_id=r["course_id"],
                code=r["course_code"],
                title=r["course_title"],
                semester_number=r["sem_number"],
                semester_label=r["sem_label"],
                section_name=r["section_name"],
                role_in_course=r["role_in_course"],
                is_active=r["is_active"],
                program_id=r["program_id"],
                program_name=r["program_name"],
                program_code=r["program_code"],
                department_id=r["department_id"],
                department_name=r["department_name"],
            )
            for r in course_rows
        ]

        return FacultyAcademicResponsibilities(
            faculty_user_id=faculty_user_id,
            home_department=home_department,
            responsibilities=responsibilities,
            departments=list(depts_seen.values()),
            programs=programs,
            course_assignments=course_entries,
        )

    @staticmethod
    async def get_faculty_summary(
        faculty_user_id: UUID, *, db: AsyncSession
    ) -> FacultyAcademicSummary:
        """Quick stats: course count, program count, department count.

        Program/department are resolved from the UNION of two sources:
          1. Explicit dean-granted coordinator scope (faculty_program_assignments),
             using the program's own (live) department — never the assignment's
             stamped department_id, which can go stale if the program is later
             moved to a different department.
          2. Programs/departments implied by the faculty's actual course-teaching
             assignments, resolved via the COURSE's own program
             (courses.program_id -> programs.acad_program_id -> acad_programs) —
             never via the semester's scheduling chain (acad_semesters ->
             acad_batches -> acad_programs), which only says WHEN a course is
             taught, not WHICH program it belongs to. The semester chain is
             used only as a fallback for courses with no acad_program_id bridge.
        """
        row = (
            await db.execute(
                text(
                    "SELECT "
                    "  (SELECT COUNT(*) FROM subject_assignments "
                    "   WHERE faculty_user_id = :uid AND is_active = true) AS course_count, "
                    "  (SELECT COUNT(DISTINCT program_id) FROM ( "
                    "     SELECT program_id FROM faculty_program_assignments "
                    "     WHERE faculty_user_id = :uid AND is_active = true "
                    "     UNION "
                    "     SELECT COALESCE(cp.acad_program_id, ab.program_id) AS program_id "
                    "     FROM subject_assignments sa "
                    "     JOIN courses c ON c.id = sa.course_id "
                    "     LEFT JOIN programs cp ON cp.id = c.program_id "
                    "     JOIN acad_semesters sem ON sem.id = sa.semester_id "
                    "     LEFT JOIN acad_batches ab ON ab.id = sem.batch_id "
                    "     WHERE sa.faculty_user_id = :uid AND sa.is_active = true "
                    "   ) all_programs WHERE program_id IS NOT NULL) AS program_count, "
                    "  (SELECT COUNT(DISTINCT department_id) FROM ( "
                    "     SELECT ap.department_id "
                    "     FROM faculty_program_assignments fpa "
                    "     JOIN acad_programs ap ON ap.id = fpa.program_id "
                    "     WHERE fpa.faculty_user_id = :uid AND fpa.is_active = true "
                    "     UNION "
                    "     SELECT COALESCE(course_ap.department_id, sem_ap.department_id) AS department_id "
                    "     FROM subject_assignments sa "
                    "     JOIN courses c ON c.id = sa.course_id "
                    "     LEFT JOIN programs cp ON cp.id = c.program_id "
                    "     LEFT JOIN acad_programs course_ap ON course_ap.id = cp.acad_program_id "
                    "     JOIN acad_semesters sem ON sem.id = sa.semester_id "
                    "     LEFT JOIN acad_batches  ab     ON ab.id  = sem.batch_id "
                    "     LEFT JOIN acad_programs sem_ap ON sem_ap.id = ab.program_id "
                    "     WHERE sa.faculty_user_id = :uid AND sa.is_active = true "
                    "   ) all_depts WHERE department_id IS NOT NULL) AS dept_count"
                ),
                {"uid": str(faculty_user_id)},
            )
        ).mappings().one()
        return FacultyAcademicSummary(
            course_count=row["course_count"] or 0,
            program_count=row["program_count"] or 0,
            department_count=row["dept_count"] or 0,
        )

    # ------------------------------------------------------------------
    # Dean governed programs
    # ------------------------------------------------------------------

    @staticmethod
    async def get_dean_programs(
        dean_user_id: UUID, *, db: AsyncSession
    ) -> list[DeanProgramOut]:
        rows = (
            await db.execute(
                text(
                    "SELECT ap.id, ap.name, ap.code, ap.degree_type, "
                    "       d.id AS dept_id, d.name AS dept_name, d.code AS dept_code, "
                    "       (SELECT COUNT(*) FROM faculty_program_assignments fpa "
                    "        WHERE fpa.program_id = ap.id AND fpa.is_active = true) AS active_faculty "
                    "FROM   dean_program_assignments dpa "
                    "JOIN   acad_programs    ap ON ap.id = dpa.program_id "
                    "LEFT   JOIN acad_departments d ON d.id = ap.department_id "
                    "WHERE  dpa.dean_user_id = :uid AND dpa.is_active = true "
                    "ORDER  BY ap.name"
                ),
                {"uid": str(dean_user_id)},
            )
        ).mappings().all()

        return [
            DeanProgramOut(
                id=r["id"],
                name=r["name"],
                code=r["code"],
                degree_type=r["degree_type"],
                department=(
                    DeptInfo(id=r["dept_id"], name=r["dept_name"], code=r["dept_code"])
                    if r["dept_id"] else None
                ),
                active_faculty_count=r["active_faculty"] or 0,
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Faculty workload (for dean faculty page)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_faculty_workload(
        program_ids: list[UUID], *, db: AsyncSession
    ) -> FacultyWorkloadResponse:
        """Return course_count and program_count per faculty for given programs."""
        if not program_ids:
            return FacultyWorkloadResponse(items=[])

        ids_str = [str(p) for p in program_ids]

        rows = (
            await db.execute(
                text(
                    "SELECT fpa.faculty_user_id, "
                    "       COUNT(DISTINCT fpa.program_id) AS program_count, "
                    "       (SELECT COUNT(*) FROM subject_assignments sa "
                    "        WHERE  sa.faculty_user_id = fpa.faculty_user_id "
                    "          AND  sa.is_active = true) AS course_count "
                    "FROM   faculty_program_assignments fpa "
                    "WHERE  fpa.program_id = ANY(:pids) AND fpa.is_active = true "
                    "GROUP  BY fpa.faculty_user_id"
                ),
                {"pids": ids_str},
            )
        ).mappings().all()

        return FacultyWorkloadResponse(
            items=[
                FacultyWorkloadItem(
                    faculty_user_id=r["faculty_user_id"],
                    course_count=r["course_count"] or 0,
                    program_count=r["program_count"] or 0,
                )
                for r in rows
            ]
        )

    # ------------------------------------------------------------------
    # Assign faculty to program
    # ------------------------------------------------------------------

    @staticmethod
    async def assign_faculty_to_program(
        body: FacultyProgramAssignCreate,
        *,
        assigned_by: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> FacultyProgramAssignOut:
        faculty = await _fetch_faculty_user(body.faculty_user_id, db)
        program = await _fetch_program_with_dept(body.program_id, db)

        # Dean scope check (ADMIN + SUPER_ADMIN bypass)
        if actor_role == "DEAN":
            await _require_dean_scope(assigned_by, body.program_id, db)

        # Duplicate check: one active assignment per (faculty, program)
        dup = (
            await db.execute(
                text(
                    "SELECT 1 FROM faculty_program_assignments "
                    "WHERE faculty_user_id = :uid AND program_id = :pid AND is_active = true "
                    "LIMIT 1"
                ),
                {"uid": str(body.faculty_user_id), "pid": str(body.program_id)},
            )
        ).one_or_none()
        if dup is not None:
            raise OwnershipServiceError(
                "DUPLICATE_ASSIGNMENT",
                "This faculty member is already actively assigned to this program.",
            )

        dept_id = program["department_id"]

        result = (
            await db.execute(
                text(
                    "INSERT INTO faculty_program_assignments "
                    "(faculty_user_id, program_id, department_id, semester_id, section_id, "
                    " is_primary, is_active, assigned_by, assigned_at) "
                    "VALUES (:uid, :pid, :did, :sid, :secid, :primary, true, :by, now()) "
                    "RETURNING id, faculty_user_id, program_id, department_id, semester_id, "
                    "          section_id, is_primary, is_active, assigned_by, assigned_at, "
                    "          revoked_by, revoked_at"
                ),
                {
                    "uid":    str(body.faculty_user_id),
                    "pid":    str(body.program_id),
                    "did":    str(dept_id) if dept_id else None,
                    "sid":    str(body.semester_id) if body.semester_id else None,
                    "secid":  str(body.section_id) if body.section_id else None,
                    "primary": body.is_primary,
                    "by":     str(assigned_by),
                },
            )
        ).mappings().one()

        await db.commit()

        await AuditService.log(
            AuditEventType.FACULTY_PROGRAM_ASSIGNED,
            actor_user_id=assigned_by,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="FacultyProgramAssignment",
            target_id=str(result["id"]),
            metadata={
                "faculty_user_id": str(body.faculty_user_id),
                "program_id":      str(body.program_id),
                "program_name":    program["name"],
                "is_primary":      body.is_primary,
            },
        )

        await notify_user(
            db,
            notification_type=NotificationType.PROGRAM_ASSIGNED,
            recipient_user_id=body.faculty_user_id,
            title="New program assigned",
            body=(
                f"You have been assigned to {program['name']}"
                + (" as program coordinator." if body.is_primary else ".")
            ),
            entity_type="FacultyProgramAssignment",
            entity_id=str(result["id"]),
        )

        return FacultyProgramAssignOut(
            id=result["id"],
            faculty_user_id=result["faculty_user_id"],
            program_id=result["program_id"],
            department_id=result["department_id"],
            semester_id=result["semester_id"],
            section_id=result["section_id"],
            is_primary=result["is_primary"],
            is_active=result["is_active"],
            assigned_by=result["assigned_by"],
            assigned_at=result["assigned_at"],
            revoked_by=result["revoked_by"],
            revoked_at=result["revoked_at"],
            program_name=program["name"],
            department_name=program["dept_name"],
            faculty_name=faculty["full_name"],
            faculty_email=faculty["email"],
        )

    # ------------------------------------------------------------------
    # Remove faculty from program
    # ------------------------------------------------------------------

    @staticmethod
    async def remove_faculty_from_program(
        assignment_id: UUID,
        *,
        revoked_by: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> FacultyProgramAssignOut:
        row = (
            await db.execute(
                text(
                    "SELECT fpa.*, "
                    "       ap.name AS program_name, d.name AS dept_name, "
                    "       u.full_name AS faculty_name, u.email AS faculty_email "
                    "FROM   faculty_program_assignments fpa "
                    "LEFT   JOIN acad_programs ap ON ap.id = fpa.program_id "
                    "LEFT   JOIN acad_departments d ON d.id = COALESCE(fpa.department_id, ap.department_id) "
                    "LEFT   JOIN users u ON u.id = fpa.faculty_user_id "
                    "WHERE  fpa.id = :id"
                ),
                {"id": str(assignment_id)},
            )
        ).mappings().one_or_none()
        if row is None:
            raise OwnershipServiceError("NOT_FOUND", "Assignment not found.", 404)
        if not row["is_active"]:
            raise OwnershipServiceError("ALREADY_REVOKED", "Assignment is already revoked.")

        # Dean scope check
        if actor_role == "DEAN":
            await _require_dean_scope(revoked_by, row["program_id"], db)

        revoked = (
            await db.execute(
                text(
                    "UPDATE faculty_program_assignments "
                    "SET is_active = false, revoked_by = :by, revoked_at = now() "
                    "WHERE id = :id "
                    "RETURNING id, faculty_user_id, program_id, department_id, semester_id, "
                    "          section_id, is_primary, is_active, assigned_by, assigned_at, "
                    "          revoked_by, revoked_at"
                ),
                {"by": str(revoked_by), "id": str(assignment_id)},
            )
        ).mappings().one()

        await db.commit()

        await AuditService.log(
            AuditEventType.FACULTY_PROGRAM_REVOKED,
            actor_user_id=revoked_by,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="FacultyProgramAssignment",
            target_id=str(assignment_id),
            metadata={
                "faculty_user_id": str(row["faculty_user_id"]),
                "program_id":      str(row["program_id"]),
                "program_name":    row["program_name"],
            },
        )

        await notify_user(
            db,
            notification_type=NotificationType.PROGRAM_ASSIGNMENT_REVOKED,
            recipient_user_id=row["faculty_user_id"],
            title="Program assignment removed",
            body=f"Your assignment to {row['program_name']} has been removed.",
            entity_type="FacultyProgramAssignment",
            entity_id=str(assignment_id),
        )

        return FacultyProgramAssignOut(
            id=revoked["id"],
            faculty_user_id=revoked["faculty_user_id"],
            program_id=revoked["program_id"],
            department_id=revoked["department_id"],
            semester_id=revoked["semester_id"],
            section_id=revoked["section_id"],
            is_primary=revoked["is_primary"],
            is_active=revoked["is_active"],
            assigned_by=revoked["assigned_by"],
            assigned_at=revoked["assigned_at"],
            revoked_by=revoked["revoked_by"],
            revoked_at=revoked["revoked_at"],
            program_name=row["program_name"],
            department_name=row["dept_name"],
            faculty_name=row["faculty_name"],
            faculty_email=row["faculty_email"],
        )

    # ------------------------------------------------------------------
    # List dean's faculty-program assignments
    # ------------------------------------------------------------------

    @staticmethod
    async def list_dean_faculty_assignments(
        dean_user_id: UUID,
        *,
        actor_role: str,
        db: AsyncSession,
    ) -> list[FacultyProgramAssignOut]:
        """All active faculty-program assignments under the dean's governed programs."""
        if actor_role == "ADMIN":
            # ADMIN sees all
            where_clause = "1=1"
            params: dict = {}
        else:
            where_clause = (
                "fpa.program_id IN ("
                "  SELECT program_id FROM dean_program_assignments "
                "  WHERE  dean_user_id = :uid AND is_active = true"
                ")"
            )
            params = {"uid": str(dean_user_id)}

        rows = (
            await db.execute(
                text(
                    "SELECT fpa.id, fpa.faculty_user_id, fpa.program_id, fpa.department_id, "
                    "       fpa.semester_id, fpa.section_id, fpa.is_primary, fpa.is_active, "
                    "       fpa.assigned_by, fpa.assigned_at, fpa.revoked_by, fpa.revoked_at, "
                    "       ap.name AS program_name, d.name AS dept_name, "
                    "       u.full_name AS faculty_name, u.email AS faculty_email "
                    "FROM   faculty_program_assignments fpa "
                    "LEFT   JOIN acad_programs    ap ON ap.id = fpa.program_id "
                    "LEFT   JOIN acad_departments d  ON d.id  = COALESCE(fpa.department_id, ap.department_id) "
                    "LEFT   JOIN users            u  ON u.id  = fpa.faculty_user_id "
                    f"WHERE  fpa.is_active = true AND {where_clause} "
                    "ORDER  BY ap.name, u.full_name"
                ),
                params,
            )
        ).mappings().all()

        return [
            FacultyProgramAssignOut(
                id=r["id"],
                faculty_user_id=r["faculty_user_id"],
                program_id=r["program_id"],
                department_id=r["department_id"],
                semester_id=r["semester_id"],
                section_id=r["section_id"],
                is_primary=r["is_primary"],
                is_active=r["is_active"],
                assigned_by=r["assigned_by"],
                assigned_at=r["assigned_at"],
                revoked_by=r["revoked_by"],
                revoked_at=r["revoked_at"],
                program_name=r["program_name"],
                department_name=r["dept_name"],
                faculty_name=r["faculty_name"],
                faculty_email=r["faculty_email"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Ownership matrix
    # ------------------------------------------------------------------

    @staticmethod
    async def get_ownership_matrix(
        program_ids: list[UUID], *, db: AsyncSession
    ) -> OwnershipMatrixOut:
        """Nested Department -> Program -> Semester -> Section -> Course -> Faculty matrix.

        The course roster per semester is the FULL catalog for that program
        (courses.program_id -> programs.acad_program_id -> acad_programs,
        matched on courses.semester = acad_semesters.number), not merely the
        courses that happen to already have an assignment — otherwise a course
        with zero faculty never appears at all, and "vacant" can't be shown.
        """
        if not program_ids:
            return OwnershipMatrixOut(departments=[])

        ids_str = [str(p) for p in program_ids]

        # Bulk-fetch programs with departments
        prog_rows = (
            await db.execute(
                text(
                    "SELECT ap.id, ap.name, ap.code, "
                    "       d.id AS dept_id, d.name AS dept_name, d.code AS dept_code "
                    "FROM   acad_programs ap "
                    "LEFT   JOIN acad_departments d ON d.id = ap.department_id "
                    "WHERE  ap.id = ANY(:pids)"
                ),
                {"pids": ids_str},
            )
        ).mappings().all()
        prog_map = {str(r["id"]): r for r in prog_rows}

        # Bulk-fetch all semesters (via batches) for these programs
        sem_rows = (
            await db.execute(
                text(
                    "SELECT s.id, s.number, s.label, b.program_id "
                    "FROM   acad_semesters s "
                    "JOIN   acad_batches   b ON b.id = s.batch_id "
                    "WHERE  b.program_id = ANY(:pids) AND s.is_active = true "
                    "ORDER  BY s.number"
                ),
                {"pids": ids_str},
            )
        ).mappings().all()

        prog_sems: dict[str, list] = {}
        for r in sem_rows:
            prog_sems.setdefault(str(r["program_id"]), []).append(r)

        def _empty_matrix() -> OwnershipMatrixOut:
            depts: dict[str, MatrixDepartment] = {}
            for pid_str in ids_str:
                if pid_str not in prog_map:
                    continue
                prog = prog_map[pid_str]
                dept_key = str(prog["dept_id"]) if prog["dept_id"] else "unassigned"
                if dept_key not in depts:
                    depts[dept_key] = MatrixDepartment(
                        department_id=prog["dept_id"],
                        name=prog["dept_name"] or "Unassigned Department",
                        code=prog["dept_code"],
                        programs=[],
                    )
                depts[dept_key].programs.append(
                    MatrixProgram(
                        program_id=pid_str,
                        name=prog["name"],
                        code=prog["code"],
                        department=(
                            DeptInfo(id=prog["dept_id"], name=prog["dept_name"], code=prog["dept_code"])
                            if prog["dept_id"] else None
                        ),
                        semesters=[],
                    )
                )
            return OwnershipMatrixOut(departments=list(depts.values()))

        sem_ids_str = [str(r["id"]) for r in sem_rows]
        if not sem_ids_str:
            return _empty_matrix()

        # Full course roster per semester = UNION of:
        #   (a) catalog-declared: courses.program_id -> curriculum
        #       programs.acad_program_id -> acad_programs, matched on
        #       courses.semester = acad_semesters.number. This is what surfaces
        #       a genuinely VACANT course (zero assignments) at all.
        #   (b) actually-assigned: subject_assignments joined straight to
        #       courses, trusting the assignment's own semester_id — never
        #       re-derived through the catalog bridge. A real, active
        #       assignment must never be invisible just because its course's
        #       catalog semester number doesn't line up with the acad_semester
        #       it was actually assigned into (a pre-existing data-alignment
        #       gap this module already guards against elsewhere, e.g.
        #       _check_program_alignment) — without (b), such a course drops
        #       out of the roster entirely, silently deflating total_courses
        #       and coverage even though Faculty Workload (which reads
        #       subject_assignments directly) still shows it.
        roster_rows = (
            await db.execute(
                text(
                    "SELECT DISTINCT semester_id, course_id, code, title, course_type FROM ( "
                    "  SELECT sem.id AS semester_id, c.id AS course_id, "
                    "         c.code, c.title, c.course_type "
                    "  FROM   acad_semesters sem "
                    "  JOIN   acad_batches ab   ON ab.id = sem.batch_id "
                    "  JOIN   programs p        ON p.acad_program_id = ab.program_id "
                    "  JOIN   courses c         ON c.program_id = p.id AND c.semester = sem.number "
                    "  WHERE  sem.id = ANY(:sids) "
                    "  UNION "
                    "  SELECT sa.semester_id, c2.id, c2.code, c2.title, c2.course_type "
                    "  FROM   subject_assignments sa "
                    "  JOIN   courses c2 ON c2.id = sa.course_id "
                    "  WHERE  sa.is_active = true AND sa.semester_id = ANY(:sids) "
                    ") roster "
                    "ORDER  BY code"
                ),
                {"sids": sem_ids_str},
            )
        ).mappings().all()

        roster_by_sem: dict[str, list] = {}
        for r in roster_rows:
            roster_by_sem.setdefault(str(r["semester_id"]), []).append(r)

        # Active sections per semester
        section_rows = (
            await db.execute(
                text(
                    "SELECT id, semester_id, name FROM acad_sections "
                    "WHERE semester_id = ANY(:sids) AND is_active = true "
                    "ORDER BY name"
                ),
                {"sids": sem_ids_str},
            )
        ).mappings().all()
        sections_by_sem: dict[str, list] = {}
        for r in section_rows:
            sections_by_sem.setdefault(str(r["semester_id"]), []).append(r)

        # Active assignments for those semesters, including section_id so a
        # course can be placed under the specific section it was assigned to
        # (NULL section_id = assigned at the whole-semester / "General" level).
        assign_rows = (
            await db.execute(
                text(
                    "SELECT sa.semester_id, sa.section_id, sa.course_id, "
                    "       sa.faculty_user_id, sa.role_in_course, "
                    "       u.full_name AS faculty_name "
                    "FROM   subject_assignments sa "
                    "JOIN   users   u ON u.id = sa.faculty_user_id "
                    "WHERE  sa.semester_id = ANY(:sids) AND sa.is_active = true "
                    "ORDER  BY u.full_name"
                ),
                {"sids": sem_ids_str},
            )
        ).mappings().all()

        # Group faculty by (semester_id, section_id-or-None, course_id)
        faculty_by_slot: dict[tuple[str, str | None, str], list[MatrixFaculty]] = {}
        general_assignment_sems: set[str] = set()
        for r in assign_rows:
            sid = str(r["semester_id"])
            secid = str(r["section_id"]) if r["section_id"] else None
            if secid is None:
                general_assignment_sems.add(sid)
            key = (sid, secid, str(r["course_id"]))
            faculty_by_slot.setdefault(key, []).append(
                MatrixFaculty(
                    user_id=r["faculty_user_id"],
                    full_name=r["faculty_name"],
                    role_in_course=r["role_in_course"],
                )
            )

        # Assemble matrix
        depts: dict[str, MatrixDepartment] = {}
        for pid_str in ids_str:
            if pid_str not in prog_map:
                continue
            prog = prog_map[pid_str]
            sems = prog_sems.get(pid_str, [])
            matrix_sems: list[MatrixSemester] = []
            for sem in sems:
                sid_str = str(sem["id"])
                roster = roster_by_sem.get(sid_str, [])
                active_sections = sections_by_sem.get(sid_str, [])

                if active_sections:
                    slot_defs: list[tuple[str | None, str]] = [
                        (str(sec["id"]), sec["name"]) for sec in active_sections
                    ]
                    if sid_str in general_assignment_sems:
                        slot_defs.append((None, "General"))
                else:
                    slot_defs = [(None, "General")]

                matrix_sections: list[MatrixSection] = []
                for sec_id, sec_name in slot_defs:
                    matrix_courses = [
                        MatrixCourse(
                            course_id=c["course_id"],
                            code=c["code"],
                            title=c["title"],
                            course_type=c["course_type"],
                            faculty=faculty_by_slot.get((sid_str, sec_id, str(c["course_id"])), []),
                        )
                        for c in roster
                    ]
                    matrix_sections.append(
                        MatrixSection(
                            section_id=sec_id,
                            name=sec_name,
                            courses=matrix_courses,
                        )
                    )

                matrix_sems.append(
                    MatrixSemester(
                        semester_id=sem["id"],
                        number=sem["number"],
                        label=sem["label"],
                        sections=matrix_sections,
                    )
                )

            dept_key = str(prog["dept_id"]) if prog["dept_id"] else "unassigned"
            if dept_key not in depts:
                depts[dept_key] = MatrixDepartment(
                    department_id=prog["dept_id"],
                    name=prog["dept_name"] or "Unassigned Department",
                    code=prog["dept_code"],
                    programs=[],
                )
            depts[dept_key].programs.append(
                MatrixProgram(
                    program_id=pid_str,
                    name=prog["name"],
                    code=prog["code"],
                    department=(
                        DeptInfo(id=prog["dept_id"], name=prog["dept_name"], code=prog["dept_code"])
                        if prog["dept_id"] else None
                    ),
                    semesters=matrix_sems,
                )
            )

        return OwnershipMatrixOut(departments=list(depts.values()))

    # ------------------------------------------------------------------
    # Dashboard summary — existing data only, no new states/approvals
    # ------------------------------------------------------------------

    @staticmethod
    async def get_dashboard_summary(
        actor_user_id: UUID, *, actor_role: str, db: AsyncSession
    ) -> OwnershipDashboardSummary:
        """Totals + vacancy + workload for the governed program set.

        ADMIN sees all active programs; DEAN sees only governed programs.
        Every figure is derived from existing tables (subject_assignments,
        faculty_program_assignments, courses) — no new state.
        """
        if actor_role == "ADMIN":
            pids = (
                await db.execute(text("SELECT id FROM acad_programs WHERE is_active = true"))
            ).scalars().all()
        else:
            programs = await OwnershipService.get_dean_programs(actor_user_id, db=db)
            pids = [p.id for p in programs]

        if not pids:
            return OwnershipDashboardSummary(
                total_programs=0, total_courses=0, total_faculty=0,
                vacant_courses=0, program_coverage_pct=0.0, faculty_workload=[],
            )

        ids_str = [str(p) for p in pids]

        # Roster = UNION of catalog-declared course slots (surfaces genuinely
        # vacant courses) and actually-assigned (course_id, semester_id) pairs
        # read straight off subject_assignments (never re-derived through the
        # catalog bridge) — see get_ownership_matrix's roster_rows for why:
        # without the union branch, a real assignment whose course.semester
        # doesn't line up with its acad_semester's number silently disappears
        # from the roster, deflating total_courses/coverage even though
        # Faculty Workload (below) still shows the same assignment.
        roster_row = (
            await db.execute(
                text(
                    "SELECT "
                    "  COUNT(*) AS total_courses, "
                    "  COUNT(*) FILTER (WHERE NOT EXISTS ( "
                    "    SELECT 1 FROM subject_assignments sa "
                    "    WHERE sa.course_id = roster.course_id AND sa.semester_id = roster.semester_id "
                    "      AND sa.is_active = true AND sa.role_in_course = 'PRIMARY' "
                    "  )) AS vacant_courses "
                    "FROM ( "
                    "  SELECT DISTINCT course_id, semester_id FROM ( "
                    "    SELECT c.id AS course_id, sem.id AS semester_id "
                    "    FROM   acad_semesters sem "
                    "    JOIN   acad_batches ab ON ab.id = sem.batch_id AND ab.is_active = true "
                    "    JOIN   programs p      ON p.acad_program_id = ab.program_id "
                    "    JOIN   courses c       ON c.program_id = p.id AND c.semester = sem.number "
                    "    WHERE  ab.program_id = ANY(:pids) AND sem.is_active = true "
                    "    UNION "
                    "    SELECT sa2.course_id, sa2.semester_id "
                    "    FROM   subject_assignments sa2 "
                    "    JOIN   acad_semesters sem2 ON sem2.id = sa2.semester_id "
                    "    JOIN   acad_batches ab2    ON ab2.id = sem2.batch_id "
                    "    WHERE  sa2.is_active = true AND ab2.program_id = ANY(:pids) "
                    "  ) combined "
                    ") roster"
                ),
                {"pids": ids_str},
            )
        ).mappings().one()

        total_courses = roster_row["total_courses"] or 0
        vacant_courses = roster_row["vacant_courses"] or 0
        coverage_pct = (
            round(100.0 * (total_courses - vacant_courses) / total_courses, 1)
            if total_courses else 0.0
        )

        workload_rows = (
            await db.execute(
                text(
                    "SELECT sa.faculty_user_id, u.full_name AS faculty_name, "
                    "       COUNT(DISTINCT sa.course_id) AS course_count, "
                    "       COUNT(DISTINCT ap.id) AS program_count "
                    "FROM   subject_assignments sa "
                    "JOIN   courses c   ON c.id = sa.course_id "
                    "JOIN   programs p  ON p.id = c.program_id "
                    "JOIN   acad_programs ap ON ap.id = p.acad_program_id "
                    "JOIN   users u     ON u.id = sa.faculty_user_id "
                    "WHERE  sa.is_active = true AND ap.id = ANY(:pids) "
                    "GROUP  BY sa.faculty_user_id, u.full_name "
                    "ORDER  BY course_count DESC, faculty_name"
                ),
                {"pids": ids_str},
            )
        ).mappings().all()

        from app.modules.m_academics.assignment_service import AssignmentService
        faculty_pool = await AssignmentService.list_faculty_users(
            caller_role=actor_role, caller_user_id=actor_user_id, db=db
        )

        return OwnershipDashboardSummary(
            total_programs=len(pids),
            total_courses=total_courses,
            total_faculty=len(faculty_pool),
            vacant_courses=vacant_courses,
            program_coverage_pct=coverage_pct,
            faculty_workload=[
                DashboardFacultyWorkload(
                    faculty_user_id=r["faculty_user_id"],
                    faculty_name=r["faculty_name"],
                    course_count=r["course_count"],
                    program_count=r["program_count"],
                )
                for r in workload_rows
            ],
        )
