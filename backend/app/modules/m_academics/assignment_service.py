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

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.modules.m_academics.assignment_repository import SubjectAssignmentRepository
from app.modules.m_academics.assignment_schemas import (
    AssignmentCreate,
    AssignmentListResponse,
    AssignmentOut,
    CourseInfo,
    FacultyInfo,
    SemesterInfo,
)
from app.modules.m_academics.models import CourseRoleInCourse, SubjectAssignment


class AssignmentServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


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
    if row["role"] != "FACULTY":
        raise AssignmentServiceError(
            "INVALID_ROLE",
            f"User role is '{row['role']}'; only FACULTY users may be assigned to courses.",
        )
    return FacultyInfo(id=row["id"], full_name=row["full_name"], email=row["email"])


async def _enrich(
    assignments: list[SubjectAssignment],
    db: AsyncSession,
) -> list[AssignmentOut]:
    """Bulk-fetch course, semester, and faculty info for a list of assignments."""
    if not assignments:
        return []

    course_ids   = list({str(a.course_id)   for a in assignments})
    semester_ids = list({str(a.semester_id)  for a in assignments})
    faculty_ids  = list({str(a.faculty_user_id) for a in assignments})

    courses_rows = (
        await db.execute(
            text("SELECT id::text, code, title FROM courses WHERE id = ANY(:ids)"),
            {"ids": course_ids},
        )
    ).mappings().all()

    semester_rows = (
        await db.execute(
            text(
                "SELECT id::text, number, label FROM acad_semesters "
                "WHERE id = ANY(:ids)"
            ),
            {"ids": semester_ids},
        )
    ).mappings().all()

    faculty_rows = (
        await db.execute(
            text("SELECT id::text, full_name, email FROM users WHERE id = ANY(:ids)"),
            {"ids": faculty_ids},
        )
    ).mappings().all()

    courses_map  = {r["id"]: r for r in courses_rows}
    semester_map = {r["id"]: r for r in semester_rows}
    faculty_map  = {r["id"]: r for r in faculty_rows}

    out = []
    for a in assignments:
        c_row = courses_map.get(str(a.course_id))
        s_row = semester_map.get(str(a.semester_id))
        f_row = faculty_map.get(str(a.faculty_user_id))
        out.append(
            AssignmentOut(
                id=a.id,
                course_id=a.course_id,
                faculty_user_id=a.faculty_user_id,
                semester_id=a.semester_id,
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
        course  = await _fetch_course(body.course_id, db)
        semester = await _fetch_semester(body.semester_id, db)
        faculty  = await _fetch_faculty(body.faculty_user_id, db)

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

        return AssignmentOut(
            id=row.id,
            course_id=row.course_id,
            faculty_user_id=row.faculty_user_id,
            semester_id=row.semester_id,
            assigned_by_user_id=row.assigned_by_user_id,
            assigned_at=row.assigned_at,
            is_active=row.is_active,
            role_in_course=row.role_in_course,
            revoked_at=row.revoked_at,
            revoked_by_user_id=row.revoked_by_user_id,
            course=course,
            semester=semester,
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
        return rows[0]

    @staticmethod
    async def list_all(
        *,
        semester_id: UUID | None = None,
        include_inactive: bool = False,
        db: AsyncSession,
    ) -> AssignmentListResponse:
        """List all assignments in the tenant (no course filter). DEAN/ADMIN only."""
        rows = await SubjectAssignmentRepository.list_all(
            semester_id=semester_id,
            include_inactive=include_inactive,
            db=db,
        )
        items = await _enrich(rows, db)
        return AssignmentListResponse(total=len(items), items=items)

    @staticmethod
    async def list_by_course(
        course_id: UUID,
        *,
        semester_id: UUID | None = None,
        include_inactive: bool = False,
        db: AsyncSession,
    ) -> AssignmentListResponse:
        rows = await SubjectAssignmentRepository.list_by_course(
            course_id, semester_id=semester_id,
            include_inactive=include_inactive, db=db
        )
        items = await _enrich(rows, db)
        return AssignmentListResponse(total=len(items), items=items)

    @staticmethod
    async def list_faculty_users(*, db: AsyncSession) -> list[dict]:
        """Return all active FACULTY users for the assignment dialog."""
        rows = (
            await db.execute(
                text(
                    "SELECT id::text, full_name, email "
                    "FROM users WHERE role = 'FACULTY' AND is_active = true "
                    "ORDER BY full_name"
                )
            )
        ).mappings().all()
        return [{"id": r["id"], "full_name": r["full_name"], "email": r["email"]} for r in rows]

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
