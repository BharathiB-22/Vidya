"""
SIS Examination Management — H59 repository.

All DB I/O lives here; the service layer owns business rules.
Complex enrichment queries use raw text() to avoid N+1 joins.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m11_sis.exam_models import (
    SisExamCenter,
    SisExamInvigilation,
    SisExamSchedule,
    SisExamSession,
)


# ─────────────────────────────────────────────────────────────────────────────
# Centers
# ─────────────────────────────────────────────────────────────────────────────

class ExamCenterRepository:

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> SisExamCenter:
        obj = SisExamCenter(
            id=uuid.uuid4(),
            created_at=datetime.now(timezone.utc),
            **data,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def get(db: AsyncSession, center_id: UUID) -> Optional[SisExamCenter]:
        result = await db.execute(
            select(SisExamCenter).where(SisExamCenter.id == center_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(db: AsyncSession, include_inactive: bool = False) -> list[SisExamCenter]:
        stmt = select(SisExamCenter)
        if not include_inactive:
            stmt = stmt.where(SisExamCenter.is_active == True)  # noqa: E712
        stmt = stmt.order_by(SisExamCenter.center_name)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update(db: AsyncSession, center_id: UUID, updates: dict) -> Optional[SisExamCenter]:
        result = await db.execute(
            select(SisExamCenter).where(SisExamCenter.id == center_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return None
        for k, v in updates.items():
            setattr(obj, k, v)
        obj.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(obj)
        return obj


# ─────────────────────────────────────────────────────────────────────────────
# Sessions
# ─────────────────────────────────────────────────────────────────────────────

class ExamSessionRepository:

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> SisExamSession:
        obj = SisExamSession(
            id=uuid.uuid4(),
            status="DRAFT",
            created_at=datetime.now(timezone.utc),
            **data,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def get(db: AsyncSession, session_id: UUID) -> Optional[SisExamSession]:
        result = await db.execute(
            select(SisExamSession).where(SisExamSession.id == session_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_semester(
        db: AsyncSession,
        semester_id: Optional[UUID] = None,
        status_filter: Optional[str] = None,
        session_type_filter: Optional[str] = None,
        visible_statuses: Optional[tuple] = None,
    ) -> list[dict]:
        """Returns sessions enriched with schedule_count."""
        conditions = ["1=1"]
        params: dict[str, Any] = {}

        if semester_id:
            conditions.append("ses.semester_id = :semester_id")
            params["semester_id"] = str(semester_id)
        if status_filter:
            conditions.append("ses.status = :status")
            params["status"] = status_filter
        if session_type_filter:
            conditions.append("ses.session_type = :session_type")
            params["session_type"] = session_type_filter
        if visible_statuses:
            placeholders = ", ".join(f":vs{i}" for i, _ in enumerate(visible_statuses))
            conditions.append(f"ses.status IN ({placeholders})")
            for i, s in enumerate(visible_statuses):
                params[f"vs{i}"] = s

        where = " AND ".join(conditions)
        sql = f"""
            SELECT
                ses.id, ses.semester_id, ses.session_type, ses.session_name,
                ses.academic_year, ses.start_date, ses.end_date, ses.status,
                ses.notes, ses.source_exam_session_id, ses.attempt_number,
                ses.hall_ticket_generated_at, ses.hall_ticket_generated_by,
                ses.created_by, ses.created_at, ses.updated_at,
                COUNT(sch.id)::int AS schedule_count
            FROM sis_exam_sessions ses
            LEFT JOIN sis_exam_schedules sch ON sch.session_id = ses.id
            WHERE {where}
            GROUP BY ses.id
            ORDER BY ses.created_at DESC
        """
        result = await db.execute(text(sql), params)
        return [dict(r._mapping) for r in result.fetchall()]

    @staticmethod
    async def update(db: AsyncSession, session_id: UUID, updates: dict) -> Optional[SisExamSession]:
        result = await db.execute(
            select(SisExamSession).where(SisExamSession.id == session_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return None
        for k, v in updates.items():
            setattr(obj, k, v)
        obj.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def delete(db: AsyncSession, session_id: UUID) -> bool:
        result = await db.execute(
            select(SisExamSession).where(SisExamSession.id == session_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return False
        await db.delete(obj)
        await db.flush()
        return True

    @staticmethod
    async def count_schedules(db: AsyncSession, session_id: UUID) -> int:
        result = await db.execute(
            text("SELECT COUNT(*) FROM sis_exam_schedules WHERE session_id = :sid"),
            {"sid": str(session_id)},
        )
        return result.scalar() or 0


# ─────────────────────────────────────────────────────────────────────────────
# Schedules
# ─────────────────────────────────────────────────────────────────────────────

class ExamScheduleRepository:

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> SisExamSchedule:
        obj = SisExamSchedule(
            id=uuid.uuid4(),
            created_at=datetime.now(timezone.utc),
            **data,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def get(db: AsyncSession, schedule_id: UUID) -> Optional[SisExamSchedule]:
        result = await db.execute(
            select(SisExamSchedule).where(SisExamSchedule.id == schedule_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_session(
        db: AsyncSession,
        session_id: UUID,
        section_id: Optional[UUID] = None,
    ) -> list[dict]:
        conditions = ["sch.session_id = :session_id"]
        params: dict[str, Any] = {"session_id": str(session_id)}
        if section_id:
            conditions.append("sch.section_id = :section_id")
            params["section_id"] = str(section_id)

        where = " AND ".join(conditions)
        sql = f"""
            SELECT
                sch.id, sch.session_id, sch.course_id, sch.section_id,
                sch.center_id, sch.exam_date, sch.start_time, sch.end_time,
                sch.room_number, sch.notes, sch.created_by, sch.created_at, sch.updated_at,
                c.code AS course_code, c.title AS course_title,
                sec.name AS section_name,
                ec.center_name
            FROM sis_exam_schedules sch
            JOIN courses c ON c.id = sch.course_id
            JOIN acad_sections sec ON sec.id = sch.section_id
            LEFT JOIN sis_exam_centers ec ON ec.id = sch.center_id
            WHERE {where}
            ORDER BY sch.exam_date, sch.start_time
        """
        result = await db.execute(text(sql), params)
        return [dict(r._mapping) for r in result.fetchall()]

    @staticmethod
    async def update(db: AsyncSession, schedule_id: UUID, updates: dict) -> Optional[SisExamSchedule]:
        result = await db.execute(
            select(SisExamSchedule).where(SisExamSchedule.id == schedule_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return None
        for k, v in updates.items():
            setattr(obj, k, v)
        obj.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def delete(db: AsyncSession, schedule_id: UUID) -> bool:
        result = await db.execute(
            select(SisExamSchedule).where(SisExamSchedule.id == schedule_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return False
        await db.delete(obj)
        await db.flush()
        return True

    @staticmethod
    async def check_duplicate(
        db: AsyncSession, session_id: UUID, course_id: UUID, section_id: UUID,
        exclude_id: Optional[UUID] = None,
    ) -> bool:
        sql = """
            SELECT 1 FROM sis_exam_schedules
            WHERE session_id = :sid AND course_id = :cid AND section_id = :secid
        """
        params: dict[str, Any] = {
            "sid": str(session_id), "cid": str(course_id), "secid": str(section_id)
        }
        if exclude_id:
            sql += " AND id <> :excl"
            params["excl"] = str(exclude_id)
        result = await db.execute(text(sql), params)
        return result.fetchone() is not None


# ─────────────────────────────────────────────────────────────────────────────
# Invigilation
# ─────────────────────────────────────────────────────────────────────────────

class ExamInvigilationRepository:

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> SisExamInvigilation:
        obj = SisExamInvigilation(
            id=uuid.uuid4(),
            created_at=datetime.now(timezone.utc),
            **data,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def get(db: AsyncSession, inv_id: UUID) -> Optional[SisExamInvigilation]:
        result = await db.execute(
            select(SisExamInvigilation).where(SisExamInvigilation.id == inv_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_session(db: AsyncSession, session_id: UUID) -> list[dict]:
        sql = """
            SELECT
                inv.id, inv.session_id, inv.schedule_id, inv.center_id,
                inv.room_number, inv.faculty_user_id, inv.assigned_by,
                inv.notes, inv.created_at,
                u.full_name AS faculty_name,
                ec.center_name,
                sch.exam_date, sch.start_time, sch.end_time
            FROM sis_exam_invigilation inv
            LEFT JOIN users u ON u.id = inv.faculty_user_id
            LEFT JOIN sis_exam_centers ec ON ec.id = inv.center_id
            LEFT JOIN sis_exam_schedules sch ON sch.id = inv.schedule_id
            WHERE inv.session_id = :session_id
            ORDER BY sch.exam_date NULLS LAST, sch.start_time NULLS LAST,
                     ec.center_name NULLS LAST, inv.room_number NULLS LAST
        """
        result = await db.execute(text(sql), {"session_id": str(session_id)})
        return [dict(r._mapping) for r in result.fetchall()]

    @staticmethod
    async def list_for_faculty(
        db: AsyncSession,
        faculty_user_id: UUID,
        session_id: Optional[UUID] = None,
    ) -> list[dict]:
        conditions = ["inv.faculty_user_id = :faculty_id"]
        params: dict[str, Any] = {"faculty_id": str(faculty_user_id)}
        if session_id:
            conditions.append("inv.session_id = :session_id")
            params["session_id"] = str(session_id)
        where = " AND ".join(conditions)
        sql = f"""
            SELECT
                inv.id, inv.session_id, inv.schedule_id, inv.center_id,
                inv.room_number, inv.faculty_user_id, inv.assigned_by,
                inv.notes, inv.created_at,
                ses.session_name,
                u.full_name AS faculty_name,
                ec.center_name,
                sch.exam_date, sch.start_time, sch.end_time
            FROM sis_exam_invigilation inv
            JOIN sis_exam_sessions ses ON ses.id = inv.session_id
            LEFT JOIN users u ON u.id = inv.faculty_user_id
            LEFT JOIN sis_exam_centers ec ON ec.id = inv.center_id
            LEFT JOIN sis_exam_schedules sch ON sch.id = inv.schedule_id
            WHERE {where}
            ORDER BY sch.exam_date NULLS LAST, sch.start_time NULLS LAST
        """
        result = await db.execute(text(sql), params)
        return [dict(r._mapping) for r in result.fetchall()]

    @staticmethod
    async def delete(db: AsyncSession, inv_id: UUID) -> bool:
        result = await db.execute(
            select(SisExamInvigilation).where(SisExamInvigilation.id == inv_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return False
        await db.delete(obj)
        await db.flush()
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Seat Allocation
# ─────────────────────────────────────────────────────────────────────────────

class ExamSeatingRepository:

    @staticmethod
    async def get_eligible_students(
        db: AsyncSession,
        semester_id: UUID,
        section_id: Optional[UUID] = None,
    ) -> list[dict]:
        """
        Returns PUBLISHED ELIGIBLE/CONDITIONAL students who already have a
        hall ticket number — the only ones who can receive a seat.
        Ordered by USN (nulls last), then full_name for deterministic assignment.
        """
        section_filter = (
            "AND ae.section_id = :section_id AND ae.is_active = true"
            if section_id else ""
        )
        section_join = (
            "JOIN acad_enrollments ae ON ae.student_id = ht.student_id"
            if section_id else ""
        )
        params: dict[str, Any] = {"semester_id": str(semester_id)}
        if section_id:
            params["section_id"] = str(section_id)

        sql = f"""
            SELECT
                ht.id AS eligibility_id,
                ht.student_id,
                COALESCE(sp.usn, '') AS usn,
                COALESCE(u.full_name, '') AS full_name
            FROM sis_hall_ticket_eligibility ht
            LEFT JOIN users u ON u.id = ht.student_id
            LEFT JOIN sis_student_profiles sp ON sp.student_user_id = ht.student_id
            {section_join}
            WHERE ht.semester_id = :semester_id
              AND ht.publish_status = 'PUBLISHED'
              AND ht.status IN ('ELIGIBLE', 'CONDITIONAL')
              AND ht.hall_ticket_number IS NOT NULL
              {section_filter}
            ORDER BY sp.usn NULLS LAST, u.full_name NULLS LAST
        """
        result = await db.execute(text(sql), params)
        return [dict(r._mapping) for r in result.fetchall()]

    @staticmethod
    async def bulk_assign_seats(
        db: AsyncSession,
        session_id: UUID,
        center_id: UUID,
        assignments: list[dict],
    ) -> int:
        """
        Bulk-update sis_hall_ticket_eligibility rows with exam location.
        Returns number of rows updated.
        """
        if not assignments:
            return 0
        update_sql = text("""
            UPDATE sis_hall_ticket_eligibility
            SET exam_session_id = :session_id,
                exam_center_id  = :center_id,
                room_number     = :room_number,
                seat_number     = :seat_number,
                updated_at      = now()
            WHERE id = :eligibility_id
        """)
        params_list = [
            {
                "session_id":    str(session_id),
                "center_id":     str(center_id),
                "room_number":   a["room_number"],
                "seat_number":   a["seat_number"],
                "eligibility_id": str(a["eligibility_id"]),
            }
            for a in assignments
        ]
        await db.execute(update_sql, params_list)
        return len(assignments)

    @staticmethod
    async def list_seating(
        db: AsyncSession,
        session_id: UUID,
        section_id: Optional[UUID] = None,
    ) -> list[dict]:
        section_filter = "AND ae.section_id = :section_id" if section_id else ""
        params: dict[str, Any] = {"session_id": str(session_id)}
        if section_id:
            params["section_id"] = str(section_id)

        sql = f"""
            SELECT
                ht.student_id,
                ht.exam_center_id,
                ht.room_number,
                ht.seat_number,
                ht.hall_ticket_number,
                COALESCE(u.full_name, '') AS student_name,
                sp.usn,
                sec.name AS section_name,
                ec.center_name
            FROM sis_hall_ticket_eligibility ht
            LEFT JOIN users u ON u.id = ht.student_id
            LEFT JOIN sis_student_profiles sp ON sp.student_user_id = ht.student_id
            LEFT JOIN acad_enrollments ae
                   ON ae.student_id = ht.student_id AND ae.is_active = true
            LEFT JOIN acad_sections sec ON sec.id = ae.section_id
            LEFT JOIN sis_exam_centers ec ON ec.id = ht.exam_center_id
            WHERE ht.exam_session_id = :session_id
              {section_filter}
            ORDER BY ht.room_number NULLS LAST, ht.seat_number NULLS LAST
        """
        result = await db.execute(text(sql), params)
        return [dict(r._mapping) for r in result.fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# Student views
# ─────────────────────────────────────────────────────────────────────────────

class ExamStudentRepository:

    @staticmethod
    async def get_student_section_for_session(
        db: AsyncSession, student_id: UUID, session_id: UUID
    ) -> Optional[dict]:
        """Returns session info + student's section_id if they are enrolled."""
        sql = """
            SELECT
                ses.id AS session_id,
                ses.session_name, ses.session_type, ses.semester_id, ses.status,
                ses.academic_year,
                COALESCE(sem.label, CONCAT('Semester ', sem.number)) AS semester_name,
                ae.section_id
            FROM sis_exam_sessions ses
            JOIN acad_semesters sem ON sem.id = ses.semester_id
            LEFT JOIN acad_enrollments ae
                   ON ae.student_id = :student_id AND ae.is_active = true
            LEFT JOIN acad_sections sec
                   ON sec.id = ae.section_id AND sec.semester_id = ses.semester_id
            WHERE ses.id = :session_id
        """
        result = await db.execute(
            text(sql), {"student_id": str(student_id), "session_id": str(session_id)}
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None

    @staticmethod
    async def get_student_seat(
        db: AsyncSession, student_id: UUID, semester_id: UUID, session_id: UUID
    ) -> Optional[dict]:
        """Returns seating info from the eligibility row for this session."""
        sql = """
            SELECT
                ht.exam_center_id, ht.room_number, ht.seat_number,
                ht.hall_ticket_number, ht.status,
                ht.created_at AS issued_at,
                ec.center_name, ec.address
            FROM sis_hall_ticket_eligibility ht
            LEFT JOIN sis_exam_centers ec ON ec.id = ht.exam_center_id
            WHERE ht.student_id   = :student_id
              AND ht.semester_id  = :semester_id
              AND ht.exam_session_id = :session_id
              AND ht.publish_status = 'PUBLISHED'
        """
        result = await db.execute(
            text(sql),
            {
                "student_id": str(student_id),
                "semester_id": str(semester_id),
                "session_id":  str(session_id),
            },
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None

    @staticmethod
    async def get_hall_ticket_row(
        db: AsyncSession, student_id: UUID, semester_id: UUID
    ) -> Optional[dict]:
        """Returns published hall ticket row (H58) for a student+semester."""
        sql = """
            SELECT
                ht.id, ht.student_id, ht.semester_id, ht.hall_ticket_number,
                ht.status, ht.exam_session_id, ht.exam_center_id,
                ht.room_number, ht.seat_number,
                ht.computed_academic_year AS academic_year,
                ht.computed_semester_name AS semester_name,
                ht.created_at AS issued_at,
                COALESCE(u.full_name, '') AS student_name,
                sp.usn,
                ec.center_name, ec.address
            FROM sis_hall_ticket_eligibility ht
            LEFT JOIN users u ON u.id = ht.student_id
            LEFT JOIN sis_student_profiles sp ON sp.student_user_id = ht.student_id
            LEFT JOIN sis_exam_centers ec ON ec.id = ht.exam_center_id
            WHERE ht.student_id   = :student_id
              AND ht.semester_id  = :semester_id
              AND ht.publish_status = 'PUBLISHED'
              AND ht.hall_ticket_number IS NOT NULL
        """
        result = await db.execute(
            text(sql), {"student_id": str(student_id), "semester_id": str(semester_id)}
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None

    @staticmethod
    async def get_timetable_for_section(
        db: AsyncSession, session_id: UUID, section_id: UUID
    ) -> list[dict]:
        sql = """
            SELECT
                sch.course_id,
                c.code AS course_code, c.title AS course_title,
                sch.exam_date, sch.start_time, sch.end_time,
                sch.room_number,
                ec.center_name
            FROM sis_exam_schedules sch
            JOIN courses c ON c.id = sch.course_id
            LEFT JOIN sis_exam_centers ec ON ec.id = sch.center_id
            WHERE sch.session_id = :session_id AND sch.section_id = :section_id
            ORDER BY sch.exam_date, sch.start_time
        """
        result = await db.execute(
            text(sql), {"session_id": str(session_id), "section_id": str(section_id)}
        )
        return [dict(r._mapping) for r in result.fetchall()]
