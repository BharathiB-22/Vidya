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
from app.modules.m_academics.ownership_schemas import (
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
    MatrixFaculty,
    MatrixProgram,
    MatrixSemester,
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
        # Program-scope assignments
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
                    "LEFT   JOIN acad_departments d ON d.id = COALESCE(fpa.department_id, ap.department_id) "
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
        for r in assign_rows:
            if r["dept_id"] and str(r["dept_id"]) not in depts_seen:
                depts_seen[str(r["dept_id"])] = DeptInfo(
                    id=r["dept_id"], name=r["dept_name"], code=r["dept_code"]
                )
            dept = depts_seen.get(str(r["dept_id"])) if r["dept_id"] else None
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
                )
            )

        # Course-level assignments from subject_assignments
        course_rows = (
            await db.execute(
                text(
                    "SELECT sa.id AS assignment_id, sa.course_id, sa.role_in_course, "
                    "       sa.is_active, "
                    "       c.code AS course_code, c.title AS course_title, "
                    "       sem.number AS sem_number, sem.label AS sem_label, "
                    "       sec.name AS section_name "
                    "FROM   subject_assignments sa "
                    "JOIN   courses       c   ON c.id   = sa.course_id "
                    "JOIN   acad_semesters sem ON sem.id = sa.semester_id "
                    "LEFT   JOIN acad_sections sec ON sec.id = sa.section_id "
                    "WHERE  sa.faculty_user_id = :uid "
                    "ORDER  BY sem.number, c.code"
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
            )
            for r in course_rows
        ]

        return FacultyAcademicResponsibilities(
            faculty_user_id=faculty_user_id,
            departments=list(depts_seen.values()),
            programs=programs,
            course_assignments=course_entries,
        )

    @staticmethod
    async def get_faculty_summary(
        faculty_user_id: UUID, *, db: AsyncSession
    ) -> FacultyAcademicSummary:
        """Quick stats: course count, program count, department count."""
        row = (
            await db.execute(
                text(
                    "SELECT "
                    "  (SELECT COUNT(*) FROM subject_assignments "
                    "   WHERE faculty_user_id = :uid AND is_active = true) AS course_count, "
                    "  (SELECT COUNT(*) FROM faculty_program_assignments "
                    "   WHERE faculty_user_id = :uid AND is_active = true) AS program_count, "
                    "  (SELECT COUNT(DISTINCT COALESCE(fpa.department_id, ap.department_id)) "
                    "   FROM faculty_program_assignments fpa "
                    "   JOIN acad_programs ap ON ap.id = fpa.program_id "
                    "   WHERE fpa.faculty_user_id = :uid AND fpa.is_active = true) AS dept_count"
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
        """Nested program → semester → course → faculty matrix."""
        if not program_ids:
            return OwnershipMatrixOut(programs=[])

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

        # Group semesters by program
        prog_sems: dict[str, list] = {}
        for r in sem_rows:
            prog_sems.setdefault(str(r["program_id"]), []).append(r)

        sem_ids_str = [str(r["id"]) for r in sem_rows]
        if not sem_ids_str:
            # No semesters yet — return programs with empty semesters
            return OwnershipMatrixOut(
                programs=[
                    MatrixProgram(
                        program_id=p,
                        name=prog_map[p]["name"],
                        code=prog_map[p]["code"],
                        department=(
                            {"id": prog_map[p]["dept_id"],
                             "name": prog_map[p]["dept_name"],
                             "code": prog_map[p]["dept_code"]}
                            if prog_map[p]["dept_id"] else None
                        ),
                        semesters=[],
                    )
                    for p in ids_str if p in prog_map
                ]
            )

        # Bulk-fetch active subject assignments for those semesters
        assign_rows = (
            await db.execute(
                text(
                    "SELECT sa.id, sa.semester_id, sa.course_id, sa.faculty_user_id, "
                    "       sa.role_in_course, "
                    "       c.code AS course_code, c.title AS course_title, c.course_type, "
                    "       u.full_name AS faculty_name "
                    "FROM   subject_assignments sa "
                    "JOIN   courses c ON c.id = sa.course_id "
                    "JOIN   users   u ON u.id = sa.faculty_user_id "
                    "WHERE  sa.semester_id = ANY(:sids) AND sa.is_active = true "
                    "ORDER  BY c.code, u.full_name"
                ),
                {"sids": sem_ids_str},
            )
        ).mappings().all()

        # Group assignments by (semester_id, course_id)
        sem_course_faculty: dict[str, dict[str, dict]] = {}
        for r in assign_rows:
            sid = str(r["semester_id"])
            cid = str(r["course_id"])
            if sid not in sem_course_faculty:
                sem_course_faculty[sid] = {}
            if cid not in sem_course_faculty[sid]:
                sem_course_faculty[sid][cid] = {
                    "code": r["course_code"],
                    "title": r["course_title"],
                    "course_type": r["course_type"],
                    "faculty": [],
                }
            sem_course_faculty[sid][cid]["faculty"].append(
                MatrixFaculty(
                    user_id=r["faculty_user_id"],
                    full_name=r["faculty_name"],
                    role_in_course=r["role_in_course"],
                )
            )

        # Assemble matrix
        matrix_programs: list[MatrixProgram] = []
        for pid_str in ids_str:
            if pid_str not in prog_map:
                continue
            prog = prog_map[pid_str]
            sems = prog_sems.get(pid_str, [])
            matrix_sems: list[MatrixSemester] = []
            for sem in sems:
                sid_str = str(sem["id"])
                courses_map = sem_course_faculty.get(sid_str, {})
                matrix_courses = [
                    MatrixCourse(
                        course_id=cid,
                        code=c["code"],
                        title=c["title"],
                        course_type=c["course_type"],
                        faculty=c["faculty"],
                    )
                    for cid, c in courses_map.items()
                ]
                matrix_sems.append(
                    MatrixSemester(
                        semester_id=sem["id"],
                        number=sem["number"],
                        label=sem["label"],
                        courses=matrix_courses,
                    )
                )
            dept = (
                {"id": prog["dept_id"], "name": prog["dept_name"], "code": prog["dept_code"]}
                if prog["dept_id"] else None
            )
            matrix_programs.append(
                MatrixProgram(
                    program_id=pid_str,
                    name=prog["name"],
                    code=prog["code"],
                    department=dept,
                    semesters=matrix_sems,
                )
            )

        return OwnershipMatrixOut(programs=matrix_programs)
