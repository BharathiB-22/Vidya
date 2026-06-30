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

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("vidya.academics.assignment")

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.modules.m_academics.assignment_repository import SubjectAssignmentRepository
from app.modules.m_academics.assignment_schemas import (
    AssignmentCreate,
    AssignmentListResponse,
    AssignmentOut,
    CourseInfo,
    FacultyInfo,
    SectionInfo,
    SemesterInfo,
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

        # Dean scope enforcement: DEAN may only assign to courses in programs they govern.
        # ADMIN and SUPER_ADMIN bypass this check.
        if actor_role == "DEAN":
            prog_row = (
                await db.execute(
                    text(
                        "SELECT acad_program_id FROM programs WHERE id = :cid LIMIT 1"
                    ),
                    {"cid": str(body.course_id)},
                )
            ).scalar_one_or_none()
            if prog_row is not None:
                scope = (
                    await db.execute(
                        text(
                            "SELECT 1 FROM dean_program_assignments "
                            "WHERE dean_user_id = :uid AND program_id = :pid AND is_active = true "
                            "LIMIT 1"
                        ),
                        {"uid": str(assigned_by), "pid": str(prog_row)},
                    )
                ).one_or_none()
                if scope is None:
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
        """Return all active users who may be assigned to courses.

        Includes FACULTY primary-role users plus DEAN users who hold an active
        FACULTY responsibility grant (DEAN+FACULTY dual-role accounts).
        """
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
                    "ORDER BY full_name"
                )
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
