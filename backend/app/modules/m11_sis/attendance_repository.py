"""
SIS Attendance — H55 Repository.

All queries run in the tenant schema (search_path injected at BEGIN).
Raw SQL (text()) is used for complex aggregations to stay performant.
ORM is used for simple single-row operations.

Key SQL conventions:
  - courses table is in tenant schema (m01_program_advisor owns it)
  - acad_* tables are in tenant schema (m_academics)
  - users table is in tenant schema (auth)
  - student_id / faculty_user_id are plain UUIDs (no FK, codebase pattern)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.models import User
from app.modules.m11_sis.attendance_models import (
    AttendanceStatus, SisAttendanceRecord, SisAttendanceSession,
)
from app.modules.m11_sis.attendance_schemas import (
    AttendanceMarkEntry, AttendanceMarkResult, AttendanceRecordOut,
    AttendanceDashboardOut, CourseAttendanceSummary,
    MyCourseAttendanceDetail, MyAttendanceSummary,
    SectionAttendanceOut, SectionStudentAttendance,
    SessionOut, SessionRecordForStudent,
    ShortageReportOut, ShortageStudentOut,
)
from app.modules.m11_sis.models import SisStudentProfile
from app.modules.m_academics.models import AcadBatch, AcadProgram, AcadSection, AcadSemester

# Default shortage threshold — configurable at query time
DEFAULT_SHORTAGE_THRESHOLD: float = 75.0


class AttendanceRepository:

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def get_session_by_id(
        session_id: UUID, db: AsyncSession,
    ) -> SisAttendanceSession | None:
        result = await db.execute(
            select(SisAttendanceSession).where(SisAttendanceSession.id == session_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_session(
        session: SisAttendanceSession, db: AsyncSession,
    ) -> SisAttendanceSession:
        db.add(session)
        await db.flush()
        await db.refresh(session)
        return session

    @staticmethod
    async def update_session(
        session: SisAttendanceSession, db: AsyncSession,
    ) -> SisAttendanceSession:
        await db.flush()
        await db.refresh(session)
        return session

    # ------------------------------------------------------------------
    # Enrolled students for a section
    # ------------------------------------------------------------------

    @staticmethod
    async def get_enrolled_student_ids(
        section_id: UUID, db: AsyncSession,
    ) -> list[UUID]:
        rows = await db.execute(
            text("""
                SELECT student_id FROM acad_enrollments
                WHERE section_id = :section_id AND is_active = TRUE
                ORDER BY student_id
            """),
            {"section_id": str(section_id)},
        )
        return [UUID(str(r[0])) for r in rows.all()]

    # ------------------------------------------------------------------
    # Elective roster sourcing — an elective course is not taken by a whole
    # section; only the students who registered for it attend. For an
    # elective session we therefore build the roster from the elective
    # registrations (intersected with the session's section so a per-section
    # sheet still only lists that section's registrants), NOT section
    # enrollment.
    # ------------------------------------------------------------------

    @staticmethod
    async def is_elective_course(course_id: UUID, db: AsyncSession) -> bool:
        row = await db.execute(
            text("""
                SELECT (is_elective OR elective_basket_id IS NOT NULL) AS is_elective
                FROM courses WHERE id = :course_id
            """),
            {"course_id": str(course_id)},
        )
        result = row.scalar_one_or_none()
        return bool(result)

    @staticmethod
    async def get_elective_registered_student_ids(
        course_id: UUID, semester_id: UUID, section_id: UUID, db: AsyncSession,
    ) -> list[UUID]:
        rows = await db.execute(
            text("""
                SELECT DISTINCT er.student_user_id
                FROM elective_registrations er
                JOIN elective_offerings eo ON eo.id = er.offering_id
                JOIN acad_enrollments ae
                     ON ae.student_id = er.student_user_id
                    AND ae.section_id = :section_id
                    AND ae.is_active = TRUE
                WHERE er.course_id = :course_id
                  AND eo.semester_id = :semester_id
                  AND er.status = 'REGISTERED'
                ORDER BY er.student_user_id
            """),
            {
                "course_id": str(course_id),
                "semester_id": str(semester_id),
                "section_id": str(section_id),
            },
        )
        return [UUID(str(r[0])) for r in rows.all()]

    # ------------------------------------------------------------------
    # Bulk create ABSENT records (called after session creation)
    # ------------------------------------------------------------------

    @staticmethod
    async def bulk_create_absent_records(
        session_id: UUID,
        student_ids: list[UUID],
        db: AsyncSession,
    ) -> int:
        if not student_ids:
            return 0
        values = [
            {"id": str(uuid.uuid4()), "session_id": str(session_id), "student_id": str(s)}
            for s in student_ids
        ]
        await db.execute(
            text("""
                INSERT INTO sis_attendance_records
                    (id, session_id, student_id, status)
                VALUES (:id, :session_id, :student_id, 'ABSENT')
                ON CONFLICT (session_id, student_id) DO NOTHING
            """),
            values,
        )
        return len(student_ids)

    # ------------------------------------------------------------------
    # Load all records for a session (returns ORM objects keyed by student_id)
    # ------------------------------------------------------------------

    @staticmethod
    async def load_records_map(
        session_id: UUID, db: AsyncSession,
    ) -> dict[UUID, SisAttendanceRecord]:
        result = await db.execute(
            select(SisAttendanceRecord)
            .where(SisAttendanceRecord.session_id == session_id)
        )
        records = result.scalars().all()
        return {r.student_id: r for r in records}

    # ------------------------------------------------------------------
    # Bulk mark / edit records (ORM update; all in one flush)
    # ------------------------------------------------------------------

    @staticmethod
    async def bulk_mark_records(
        records_map: dict[UUID, SisAttendanceRecord],
        entries: list[AttendanceMarkEntry],
        actor_id: UUID,
        edit_reason: Optional[str],
        db: AsyncSession,
    ) -> tuple[int, int, int]:
        """
        Apply entries to existing records in-memory, then flush once.

        Returns (saved, first_marks, edits).
        - first_marks: records where marked_by was None before this call
        - edits: records where marked_by was already set
        """
        now = datetime.now(timezone.utc)
        saved = first_marks = edits = 0

        for entry in entries:
            record = records_map.get(entry.student_id)
            if record is None:
                continue  # student not in this section; skip silently

            record.status  = entry.status
            record.remarks = entry.remarks

            if record.marked_by is None:
                record.marked_by = actor_id
                record.marked_at = now
                first_marks += 1
            else:
                record.edited_by   = actor_id
                record.edited_at   = now
                record.edit_reason = edit_reason
                edits += 1

            saved += 1

        await db.flush()
        return saved, first_marks, edits

    # ------------------------------------------------------------------
    # Single record edit
    # ------------------------------------------------------------------

    @staticmethod
    async def get_record_by_id(
        record_id: UUID, db: AsyncSession,
    ) -> SisAttendanceRecord | None:
        result = await db.execute(
            select(SisAttendanceRecord).where(SisAttendanceRecord.id == record_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def edit_record(
        record: SisAttendanceRecord,
        status: str,
        remarks: Optional[str],
        actor_id: UUID,
        edit_reason: Optional[str],
        db: AsyncSession,
    ) -> SisAttendanceRecord:
        now = datetime.now(timezone.utc)
        record.status  = status
        record.remarks = remarks
        if record.marked_by is None:
            record.marked_by = actor_id
            record.marked_at = now
        else:
            record.edited_by   = actor_id
            record.edited_at   = now
            record.edit_reason = edit_reason
        await db.flush()
        await db.refresh(record)
        return record

    # ------------------------------------------------------------------
    # Enriched session records (with student name, USN)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_records_by_session(
        session_id: UUID, db: AsyncSession,
    ) -> list[AttendanceRecordOut]:
        rows = await db.execute(
            select(
                SisAttendanceRecord.id,
                SisAttendanceRecord.session_id,
                SisAttendanceRecord.student_id,
                SisAttendanceRecord.status,
                SisAttendanceRecord.remarks,
                SisAttendanceRecord.marked_by,
                SisAttendanceRecord.marked_at,
                SisAttendanceRecord.edited_by,
                SisAttendanceRecord.edited_at,
                SisAttendanceRecord.edit_reason,
                User.full_name.label("student_name"),
                User.email.label("student_email"),
                SisStudentProfile.usn,
            )
            .join(User, User.id == SisAttendanceRecord.student_id)
            .outerjoin(SisStudentProfile, SisStudentProfile.user_id == SisAttendanceRecord.student_id)
            .where(SisAttendanceRecord.session_id == session_id)
            .order_by(User.full_name)
        )
        return [
            AttendanceRecordOut(
                id=r.id, session_id=r.session_id, student_id=r.student_id,
                student_name=r.student_name, student_email=r.student_email, usn=r.usn,
                status=r.status, remarks=r.remarks,
                marked_by=r.marked_by, marked_at=r.marked_at,
                edited_by=r.edited_by, edited_at=r.edited_at, edit_reason=r.edit_reason,
            )
            for r in rows.all()
        ]

    # ------------------------------------------------------------------
    # List sessions with full enrichment (one SQL query)
    # ------------------------------------------------------------------

    @staticmethod
    async def list_sessions_enriched(
        *,
        faculty_user_id: Optional[UUID] = None,
        course_id:       Optional[UUID] = None,
        section_id:      Optional[UUID] = None,
        date_from:       Optional[str]  = None,
        date_to:         Optional[str]  = None,
        status:          Optional[str]  = None,
        db: AsyncSession,
    ) -> list[dict]:
        filters = ["1=1"]
        params: dict = {}

        if faculty_user_id is not None:
            filters.append("s.faculty_user_id = :faculty_user_id")
            params["faculty_user_id"] = str(faculty_user_id)
        if course_id is not None:
            filters.append("s.course_id = :course_id")
            params["course_id"] = str(course_id)
        if section_id is not None:
            filters.append("s.section_id = :section_id")
            params["section_id"] = str(section_id)
        if date_from is not None:
            filters.append("s.session_date >= :date_from")
            params["date_from"] = date_from
        if date_to is not None:
            filters.append("s.session_date <= :date_to")
            params["date_to"] = date_to
        if status is not None:
            filters.append("s.status = :status")
            params["status"] = status

        where = " AND ".join(filters)
        rows = await db.execute(
            text(f"""
                SELECT
                    s.id, s.course_id, s.section_id, s.faculty_user_id,
                    s.session_date, s.period_number, s.duration_minutes, s.topic_covered,
                    s.status, s.first_marked_at, s.locked_at,
                    s.reopened_by, s.reopened_at, s.reopen_reason,
                    s.created_at, s.updated_at,
                    c.code  AS course_code,
                    c.title AS course_title,
                    sect.name   AS section_name,
                    sem.number  AS semester_number,
                    u.full_name AS faculty_name,
                    COUNT(r.id) FILTER (WHERE r.status = 'PRESENT') AS present_count,
                    COUNT(r.id) FILTER (WHERE r.status = 'ABSENT')  AS absent_count,
                    COUNT(r.id) AS total_enrolled
                FROM sis_attendance_sessions s
                JOIN courses c          ON c.id    = s.course_id
                JOIN acad_sections sect ON sect.id = s.section_id
                JOIN acad_semesters sem ON sem.id  = sect.semester_id
                JOIN users u            ON u.id    = s.faculty_user_id
                LEFT JOIN sis_attendance_records r ON r.session_id = s.id
                WHERE {where}
                GROUP BY s.id, c.code, c.title, sect.name, sem.number, u.full_name
                ORDER BY s.session_date DESC, s.period_number NULLS LAST
            """),
            params,
        )
        return [dict(r._mapping) for r in rows.all()]

    # ------------------------------------------------------------------
    # Student attendance summary (across all courses in their section)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_student_summary_raw(
        student_id: UUID,
        threshold: float,
        db: AsyncSession,
    ) -> tuple[User | None, SisStudentProfile | None, list[dict]]:
        user = (await db.execute(
            select(User).where(User.id == student_id)
        )).scalar_one_or_none()

        profile = (await db.execute(
            select(SisStudentProfile).where(SisStudentProfile.user_id == student_id)
        )).scalar_one_or_none()

        rows = await db.execute(
            text("""
                SELECT
                    s.course_id::text,
                    c.code  AS course_code,
                    c.title AS course_title,
                    COUNT(*)                                     AS total_sessions,
                    COUNT(*) FILTER (WHERE r.status = 'PRESENT') AS attended_count
                FROM sis_attendance_records r
                JOIN sis_attendance_sessions s ON s.id = r.session_id
                JOIN courses c                 ON c.id = s.course_id
                WHERE r.student_id = :student_id
                GROUP BY s.course_id, c.code, c.title
                ORDER BY c.code
            """),
            {"student_id": str(student_id)},
        )
        return user, profile, [dict(r._mapping) for r in rows.all()]

    @staticmethod
    async def get_student_course_sessions(
        student_id: UUID,
        course_id: UUID,
        db: AsyncSession,
    ) -> list[dict]:
        rows = await db.execute(
            text("""
                SELECT
                    s.id::text AS session_id,
                    s.session_date,
                    s.period_number,
                    s.topic_covered,
                    r.status,
                    r.remarks
                FROM sis_attendance_records r
                JOIN sis_attendance_sessions s ON s.id = r.session_id
                WHERE r.student_id = :student_id AND s.course_id = :course_id
                ORDER BY s.session_date DESC, s.period_number NULLS LAST
            """),
            {"student_id": str(student_id), "course_id": str(course_id)},
        )
        return [dict(r._mapping) for r in rows.all()]

    # ------------------------------------------------------------------
    # Per-student % for threshold notification check
    # ------------------------------------------------------------------

    @staticmethod
    async def get_students_course_pct_batch(
        student_ids: list[UUID],
        course_id: UUID,
        section_id: UUID,
        db: AsyncSession,
    ) -> dict[UUID, Optional[float]]:
        if not student_ids:
            return {}
        rows = await db.execute(
            text("""
                SELECT
                    r.student_id::text,
                    COUNT(*) FILTER (WHERE r.status = 'PRESENT') AS attended,
                    COUNT(*)                                     AS countable
                FROM sis_attendance_records r
                JOIN sis_attendance_sessions s ON s.id = r.session_id
                WHERE r.student_id = ANY(:sids::uuid[])
                  AND s.course_id  = :course_id
                  AND s.section_id = :section_id
                GROUP BY r.student_id
            """),
            {
                "sids":       [str(s) for s in student_ids],
                "course_id":  str(course_id),
                "section_id": str(section_id),
            },
        )
        result = {}
        for row in rows.all():
            sid = UUID(str(row.student_id))
            pct = round(row.attended / row.countable * 100, 2) if row.countable > 0 else None
            result[sid] = pct
        return result

    # ------------------------------------------------------------------
    # Section analytics
    # ------------------------------------------------------------------

    @staticmethod
    async def get_section_analytics_raw(
        section_id: UUID, threshold: float, db: AsyncSession,
    ) -> tuple[dict, list[dict]]:
        section_row = (await db.execute(
            select(
                AcadSection.id, AcadSection.name, AcadSection.semester_id,
            ).where(AcadSection.id == section_id)
        )).one_or_none()
        if section_row is None:
            return {}, []

        # Fetch semester + batch + program for context
        sem = (await db.execute(
            select(AcadSemester).where(AcadSemester.id == section_row.semester_id)
        )).scalar_one_or_none()
        context: dict = {
            "section_id":       section_id,
            "section_name":     section_row.name,
            "semester_number":  sem.number if sem else 0,
            "batch_name":       "",
            "program_name":     "",
        }
        if sem:
            batch = (await db.execute(
                select(AcadBatch).where(AcadBatch.id == sem.batch_id)
            )).scalar_one_or_none()
            if batch:
                context["batch_name"] = batch.name
                prog = (await db.execute(
                    select(AcadProgram).where(AcadProgram.id == batch.program_id)
                )).scalar_one_or_none()
                if prog:
                    context["program_name"] = prog.name

        # Student-level aggregation for this section
        rows = await db.execute(
            text("""
                SELECT
                    r.student_id::text,
                    u.full_name,
                    sp.usn,
                    COUNT(*)                                     AS total_sessions,
                    COUNT(*) FILTER (WHERE r.status = 'PRESENT') AS attended_count
                FROM sis_attendance_records r
                JOIN sis_attendance_sessions s ON s.id = r.session_id
                JOIN users u                   ON u.id = r.student_id
                LEFT JOIN sis_student_profiles sp ON sp.user_id = r.student_id
                WHERE s.section_id = :section_id
                GROUP BY r.student_id, u.full_name, sp.usn
                ORDER BY u.full_name
            """),
            {"section_id": str(section_id)},
        )
        return context, [dict(r._mapping) for r in rows.all()]

    # ------------------------------------------------------------------
    # Shortage report
    # ------------------------------------------------------------------

    @staticmethod
    async def get_shortage_raw(
        threshold: float,
        semester_id: Optional[UUID],
        section_id:  Optional[UUID],
        course_id:   Optional[UUID],
        db: AsyncSession,
        *,
        program_id:     Optional[UUID] = None,
        batch_id:       Optional[UUID] = None,
        finalized_only: bool = False,
        allowed_program_ids: Optional[list[UUID]] = None,
    ) -> list[dict]:
        """
        Returns per-student, per-course shortage rows.

        New keyword-only params (H56):
          program_id     — restrict to one academic program
          batch_id       — restrict to one batch
          finalized_only — when True, count only LOCKED sessions (finalized data)

        allowed_program_ids — DEAN-scope enforcement (Phase 2 refinements):
          when provided, restricts rows to sessions whose academic program is
          in this set, regardless of the client-supplied `program_id`. Kept
          distinct from `program_id` (which is a client convenience filter)
          so scope enforcement can never be bypassed by omitting `program_id`.

        Adds sem.number to the raw dict so callers can build grouped views
        without secondary lookups.
        """
        extra_filters: list[str] = []
        extra_joins:   list[str] = []
        params: dict = {"threshold": threshold}

        if semester_id:
            extra_filters.append("AND sect.semester_id = :semester_id")
            params["semester_id"] = str(semester_id)
        if section_id:
            extra_filters.append("AND s.section_id = :section_id")
            params["section_id"] = str(section_id)
        if course_id:
            extra_filters.append("AND s.course_id = :course_id")
            params["course_id"] = str(course_id)
        if finalized_only:
            # Only sessions whose status is LOCKED are included; OPEN / REOPENED
            # sessions may still be edited so they are excluded from finalized reports.
            extra_filters.append("AND s.status = 'LOCKED'")
        if batch_id or program_id or allowed_program_ids is not None:
            extra_joins.append("JOIN acad_semesters _sem ON _sem.id = sect.semester_id")
            extra_joins.append("JOIN acad_batches   _bat ON _bat.id = _sem.batch_id")
            if batch_id:
                extra_filters.append("AND _bat.id = :batch_id")
                params["batch_id"] = str(batch_id)
            if program_id or allowed_program_ids is not None:
                extra_joins.append("JOIN acad_programs _prog ON _prog.id = _bat.program_id")
                if program_id:
                    extra_filters.append("AND _prog.id = :program_id")
                    params["program_id"] = str(program_id)
                if allowed_program_ids is not None:
                    extra_filters.append("AND _prog.id = ANY(:allowed_program_ids)")
                    params["allowed_program_ids"] = [str(p) for p in allowed_program_ids]

        joins_sql = "\n                    ".join(extra_joins)
        where_sql  = "\n                    ".join(extra_filters)

        rows = await db.execute(
            text(f"""
                WITH stats AS (
                    SELECT
                        r.student_id,
                        s.course_id,
                        s.section_id,
                        COUNT(*)                                     AS total_sessions,
                        COUNT(*) FILTER (WHERE r.status = 'PRESENT') AS attended_count
                    FROM sis_attendance_records r
                    JOIN sis_attendance_sessions s ON s.id = r.session_id
                    JOIN acad_sections sect        ON sect.id = s.section_id
                    {joins_sql}
                    WHERE 1=1
                    {where_sql}
                    GROUP BY r.student_id, s.course_id, s.section_id
                ),
                with_pct AS (
                    SELECT *,
                        CASE WHEN total_sessions > 0
                             THEN ROUND((attended_count::numeric / total_sessions) * 100, 2)
                             ELSE NULL
                        END AS attendance_pct
                    FROM stats
                )
                SELECT
                    wp.student_id::text,
                    u.full_name   AS student_name,
                    sp.usn,
                    u.email,
                    wp.section_id::text,
                    sect.name     AS section_name,
                    sem.number    AS semester_number,
                    wp.course_id::text,
                    c.code        AS course_code,
                    c.title       AS course_title,
                    wp.total_sessions,
                    wp.attended_count AS attended_sessions,
                    wp.attendance_pct
                FROM with_pct wp
                JOIN users u            ON u.id    = wp.student_id
                JOIN courses c          ON c.id    = wp.course_id
                JOIN acad_sections sect ON sect.id = wp.section_id
                JOIN acad_semesters sem ON sem.id  = sect.semester_id
                LEFT JOIN sis_student_profiles sp ON sp.user_id = wp.student_id
                WHERE wp.attendance_pct < :threshold
                ORDER BY wp.attendance_pct ASC NULLS LAST, u.full_name
            """),
            params,
        )
        return [dict(r._mapping) for r in rows.all()]

    @staticmethod
    async def get_faculty_shortage_raw(
        faculty_user_id: UUID,
        threshold: float,
        db: AsyncSession,
        *,
        course_id:      Optional[UUID] = None,
        section_id:     Optional[UUID] = None,
        finalized_only: bool = False,
    ) -> list[dict]:
        """
        Shortage rows scoped to courses where the faculty holds an active
        PRIMARY or CO_FACULTY subject assignment.

        Returns the same row shape as get_shortage_raw(), plus:
          semester_number  — for grouping
          total_enrolled   — enrolled students in that section (for context ratio)
        """
        extra_filters: list[str] = []
        params: dict = {
            "threshold":       threshold,
            "faculty_user_id": str(faculty_user_id),
        }

        if course_id:
            extra_filters.append("AND s.course_id = :course_id")
            params["course_id"] = str(course_id)
        if section_id:
            extra_filters.append("AND s.section_id = :section_id")
            params["section_id"] = str(section_id)
        if finalized_only:
            extra_filters.append("AND s.status = 'LOCKED'")

        where = "\n                    ".join(extra_filters)

        rows = await db.execute(
            text(f"""
                WITH faculty_courses AS (
                    SELECT DISTINCT course_id, semester_id
                    FROM subject_assignments
                    WHERE faculty_user_id = :faculty_user_id
                      AND is_active = TRUE
                      AND role_in_course IN ('PRIMARY', 'CO_FACULTY')
                ),
                stats AS (
                    SELECT
                        r.student_id,
                        s.course_id,
                        s.section_id,
                        COUNT(*)                                     AS total_sessions,
                        COUNT(*) FILTER (WHERE r.status = 'PRESENT') AS attended_count
                    FROM sis_attendance_records r
                    JOIN sis_attendance_sessions s ON s.id = r.session_id
                    JOIN acad_sections sect        ON sect.id = s.section_id
                    JOIN faculty_courses fc        ON fc.course_id   = s.course_id
                                                 AND fc.semester_id  = sect.semester_id
                    WHERE 1=1
                    {where}
                    GROUP BY r.student_id, s.course_id, s.section_id
                ),
                with_pct AS (
                    SELECT *,
                        CASE WHEN total_sessions > 0
                             THEN ROUND((attended_count::numeric / total_sessions) * 100, 2)
                             ELSE NULL
                        END AS attendance_pct
                    FROM stats
                )
                SELECT
                    wp.student_id::text,
                    u.full_name   AS student_name,
                    sp.usn,
                    u.email,
                    wp.section_id::text,
                    sect.name     AS section_name,
                    sem.number    AS semester_number,
                    wp.course_id::text,
                    c.code        AS course_code,
                    c.title       AS course_title,
                    wp.total_sessions,
                    wp.attended_count AS attended_sessions,
                    wp.attendance_pct,
                    COALESCE(enroll_counts.total_enrolled, 0) AS total_enrolled
                FROM with_pct wp
                JOIN users u            ON u.id    = wp.student_id
                JOIN courses c          ON c.id    = wp.course_id
                JOIN acad_sections sect ON sect.id = wp.section_id
                JOIN acad_semesters sem ON sem.id  = sect.semester_id
                LEFT JOIN sis_student_profiles sp ON sp.user_id = wp.student_id
                LEFT JOIN (
                    SELECT section_id, COUNT(*) AS total_enrolled
                    FROM acad_enrollments
                    WHERE is_active = TRUE
                    GROUP BY section_id
                ) enroll_counts ON enroll_counts.section_id = wp.section_id
                WHERE wp.attendance_pct < :threshold
                ORDER BY c.code, sect.name, wp.attendance_pct ASC NULLS LAST
            """),
            params,
        )
        return [dict(r._mapping) for r in rows.all()]

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    @staticmethod
    async def get_dashboard_raw(
        threshold: float,
        semester_id: Optional[UUID],
        db: AsyncSession,
        *,
        allowed_program_ids: Optional[list[UUID]] = None,
    ) -> dict:
        sem_filter = "AND sect.semester_id = :semester_id" if semester_id else ""
        params: dict = {"threshold": threshold}
        if semester_id:
            params["semester_id"] = str(semester_id)

        prog_join_top = ""
        prog_filter_top = ""
        prog_join_below = ""
        prog_filter_below = ""
        if allowed_program_ids is not None:
            prog_join_top = (
                "JOIN acad_sections _sect2 ON _sect2.id = s.section_id "
                "JOIN acad_semesters _sem2 ON _sem2.id = _sect2.semester_id "
                "JOIN acad_batches _bat2   ON _bat2.id = _sem2.batch_id "
                "JOIN acad_programs _prog2 ON _prog2.id = _bat2.program_id"
            )
            prog_filter_top = "AND _prog2.id = ANY(:allowed_program_ids)"
            prog_join_below = (
                "JOIN acad_batches _bat ON _bat.id = _sem.batch_id "
                "JOIN acad_programs _prog ON _prog.id = _bat.program_id"
            )
            prog_filter_below = "AND _prog.id = ANY(:allowed_program_ids)"
            params["allowed_program_ids"] = [str(p) for p in allowed_program_ids]

        row = (await db.execute(
            text(f"""
                SELECT
                    COUNT(*) FILTER (WHERE s.session_date = CURRENT_DATE)                    AS today_sessions,
                    COUNT(*) FILTER (WHERE s.session_date = CURRENT_DATE
                                    AND s.first_marked_at IS NOT NULL)                       AS marked_today,
                    COUNT(*) FILTER (WHERE s.session_date <= CURRENT_DATE
                                    AND s.first_marked_at IS NULL)                           AS pending_sessions
                FROM sis_attendance_sessions s
                {prog_join_top}
                WHERE 1=1 {prog_filter_top}
            """),
            params,
        )).one()

        # Students below threshold (more expensive — separate query)
        below_row = (await db.execute(
            text(f"""
                WITH stats AS (
                    SELECT
                        r.student_id,
                        s.course_id,
                        COUNT(*) FILTER (WHERE r.status = 'PRESENT') AS attended_count,
                        COUNT(*)                                     AS total_sessions
                    FROM sis_attendance_records r
                    JOIN sis_attendance_sessions s ON s.id = r.session_id
                    JOIN acad_sections sect        ON sect.id = s.section_id
                    JOIN acad_semesters _sem       ON _sem.id = sect.semester_id
                    {prog_join_below}
                    WHERE 1=1 {sem_filter}
                    {prog_filter_below}
                    GROUP BY r.student_id, s.course_id
                )
                SELECT COUNT(DISTINCT student_id) AS cnt
                FROM stats
                WHERE total_sessions > 0
                  AND ROUND(
                      (attended_count::numeric / NULLIF(total_sessions, 0)) * 100,
                      2) < :threshold
            """),
            params,
        )).one()

        return {
            "today_sessions":           row.today_sessions or 0,
            "marked_today":             row.marked_today or 0,
            "pending_sessions":         row.pending_sessions or 0,
            "students_below_threshold": below_row.cnt or 0,
            "threshold_pct":            threshold,
        }

    # ------------------------------------------------------------------
    # Notification deduplication check
    # ------------------------------------------------------------------

    @staticmethod
    async def check_shortage_warning_exists(
        student_id: UUID,
        course_id:  UUID,
        section_id: UUID,
        db: AsyncSession,
    ) -> bool:
        entity_id = f"{course_id}:{section_id}"
        row = await db.execute(
            text("""
                SELECT 1 FROM notifications
                WHERE recipient_user_id = :student_id
                  AND notification_type = 'ATTENDANCE_SHORTAGE_WARNING'
                  AND entity_id = :entity_id
                LIMIT 1
            """),
            {"student_id": str(student_id), "entity_id": entity_id},
        )
        return row.scalar_one_or_none() is not None
