"""
SIS Internal Marks — H57 Repository.

All DB operations for sis_marks_components and sis_marks_entries.
Raw SQL used for analytics; ORM used for CRUD.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m11_sis.marks_models import SisMarksComponent, SisMarksEntry


class MarksRepository:

    # ------------------------------------------------------------------
    # Components — CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def create_component(component: SisMarksComponent, db: AsyncSession) -> SisMarksComponent:
        db.add(component)
        await db.flush()
        await db.refresh(component)
        return component

    @staticmethod
    async def get_component_by_id(component_id: UUID, db: AsyncSession) -> Optional[SisMarksComponent]:
        return (
            await db.execute(
                select(SisMarksComponent).where(
                    SisMarksComponent.id == component_id,
                    SisMarksComponent.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    async def update_component(component: SisMarksComponent, db: AsyncSession) -> SisMarksComponent:
        await db.flush()
        await db.refresh(component)
        return component

    @staticmethod
    async def list_components_enriched(
        *,
        course_id:   Optional[UUID] = None,
        section_id:  Optional[UUID] = None,
        semester_id: Optional[UUID] = None,
        status:      Optional[str]  = None,
        faculty_id:  Optional[UUID] = None,
        db: AsyncSession,
    ) -> list[dict]:
        """
        Returns component rows joined with course + section info plus fill counts.
        """
        filters = ["mc.is_active = true"]
        params: dict = {}

        if course_id:
            filters.append("mc.course_id = :course_id")
            params["course_id"] = str(course_id)
        if section_id:
            filters.append("mc.section_id = :section_id")
            params["section_id"] = str(section_id)
        if semester_id:
            filters.append("mc.semester_id = :semester_id")
            params["semester_id"] = str(semester_id)
        if status:
            filters.append("mc.status = :status")
            params["status"] = status
        if faculty_id:
            filters.append("mc.created_by = :faculty_id")
            params["faculty_id"] = str(faculty_id)

        where_clause = " AND ".join(filters)

        sql = text(f"""
            SELECT
                mc.id,
                mc.course_id,
                c.code            AS course_code,
                c.title           AS course_title,
                mc.section_id,
                s.name            AS section_name,
                mc.semester_id,
                mc.created_by,
                mc.component_type,
                mc.name,
                mc.max_marks,
                mc.weightage,
                mc.due_date,
                mc.display_order,
                mc.status,
                mc.published_at,
                mc.locked_at,
                mc.locked_by,
                mc.reopened_by,
                mc.reopened_at,
                mc.reopen_reason,
                mc.is_active,
                mc.created_at,
                mc.updated_at,
                -- fill counts
                COALESCE(fill.total_entries, 0)  AS entries_count,
                COALESCE(fill.filled_entries, 0) AS filled_count
            FROM sis_marks_components mc
            LEFT JOIN courses         c  ON c.id  = mc.course_id
            LEFT JOIN acad_sections   s  ON s.id  = mc.section_id
            LEFT JOIN (
                SELECT
                    component_id,
                    COUNT(*)                                     AS total_entries,
                    COUNT(marks_obtained)                        AS filled_entries
                FROM sis_marks_entries
                GROUP BY component_id
            ) fill ON fill.component_id = mc.id
            WHERE {where_clause}
            ORDER BY mc.display_order NULLS LAST, mc.created_at
        """)

        result = await db.execute(sql, params)
        return [dict(row) for row in result.mappings().all()]

    # ------------------------------------------------------------------
    # Entries — CRUD and UPSERT
    # ------------------------------------------------------------------

    @staticmethod
    async def get_entry_by_id(entry_id: UUID, db: AsyncSession) -> Optional[SisMarksEntry]:
        return (
            await db.execute(select(SisMarksEntry).where(SisMarksEntry.id == entry_id))
        ).scalar_one_or_none()

    @staticmethod
    async def get_entry(component_id: UUID, student_id: UUID, db: AsyncSession) -> Optional[SisMarksEntry]:
        return (
            await db.execute(
                select(SisMarksEntry).where(
                    SisMarksEntry.component_id == component_id,
                    SisMarksEntry.student_id   == student_id,
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    async def get_entries_enriched(component_id: UUID, db: AsyncSession) -> list[dict]:
        sql = text("""
            SELECT
                me.id,
                me.component_id,
                me.student_id,
                u.full_name     AS student_name,
                sp.usn,
                u.email,
                me.marks_obtained,
                me.remarks,
                me.marked_by,
                me.marked_at,
                me.edited_by,
                me.edited_at,
                me.edit_reason,
                me.created_at,
                me.updated_at
            FROM sis_marks_entries me
            JOIN  users              u  ON u.id  = me.student_id
            LEFT JOIN sis_student_profiles sp ON sp.user_id = me.student_id
            WHERE me.component_id = :component_id
            ORDER BY sp.usn NULLS LAST, u.full_name
        """)
        result = await db.execute(sql, {"component_id": str(component_id)})
        return [dict(row) for row in result.mappings().all()]

    @staticmethod
    async def get_enrolled_students(section_id: UUID, db: AsyncSession) -> list[dict]:
        """Returns active enrolled students for a section with profile info."""
        sql = text("""
            SELECT
                ae.student_id,
                u.full_name,
                u.email,
                sp.usn
            FROM acad_enrollments      ae
            JOIN  users                u   ON u.id  = ae.student_id AND u.is_active = true
            LEFT JOIN sis_student_profiles sp ON sp.user_id = ae.student_id
            WHERE ae.section_id  = :section_id
              AND ae.is_active   = true
            ORDER BY sp.usn NULLS LAST, u.full_name
        """)
        result = await db.execute(sql, {"section_id": str(section_id)})
        return [dict(row) for row in result.mappings().all()]

    @staticmethod
    async def bulk_upsert_entries(
        *,
        component_id: UUID,
        entries: list[dict],   # each: {student_id, marks_obtained, remarks}
        actor_id: UUID,
        edit_reason: Optional[str],
        is_first_bulk: bool,
        db: AsyncSession,
    ) -> tuple[int, int, int]:
        """
        UPSERT all entries.  Returns (saved, first_marks, edits).
        first_bulk = True means this is the first time any mark is being saved.
        """
        now = datetime.now(timezone.utc)
        saved = first_marks = edits = 0

        for item in entries:
            sid = item["student_id"]
            marks = item.get("marks_obtained")
            remarks = item.get("remarks")

            existing = await db.execute(
                select(SisMarksEntry).where(
                    SisMarksEntry.component_id == component_id,
                    SisMarksEntry.student_id   == sid,
                )
            )
            entry = existing.scalar_one_or_none()

            if entry is None:
                entry = SisMarksEntry(
                    id=uuid.uuid4(),
                    component_id=component_id,
                    student_id=sid,
                    marks_obtained=marks,
                    remarks=remarks,
                    marked_by=actor_id,
                    marked_at=now,
                    created_at=now,
                    updated_at=now,
                )
                db.add(entry)
                first_marks += 1
            else:
                if entry.marked_by is None:
                    entry.marked_by = actor_id
                    entry.marked_at = now
                    first_marks += 1
                else:
                    entry.edited_by   = actor_id
                    entry.edited_at   = now
                    entry.edit_reason = edit_reason
                    edits += 1
                entry.marks_obtained = marks
                if remarks is not None:
                    entry.remarks = remarks
                entry.updated_at = now
            saved += 1

        await db.flush()
        return saved, first_marks, edits

    @staticmethod
    async def update_entry(entry: SisMarksEntry, db: AsyncSession) -> SisMarksEntry:
        await db.flush()
        await db.refresh(entry)
        return entry

    # ------------------------------------------------------------------
    # Analytics: section report
    # ------------------------------------------------------------------

    @staticmethod
    async def get_section_marks_raw(section_id: UUID, course_id: Optional[UUID], db: AsyncSession) -> list[dict]:
        """Per-student marks summary across all PUBLISHED/LOCKED components."""
        params: dict = {"section_id": str(section_id)}
        course_filter = ""
        if course_id:
            course_filter = "AND mc.course_id = :course_id"
            params["course_id"] = str(course_id)

        sql = text(f"""
            SELECT
                ae.student_id,
                u.full_name     AS student_name,
                sp.usn,
                mc.id           AS component_id,
                mc.max_marks,
                me.marks_obtained
            FROM acad_enrollments  ae
            JOIN  users            u   ON u.id  = ae.student_id
            LEFT JOIN sis_student_profiles sp ON sp.user_id = ae.student_id
            CROSS JOIN sis_marks_components mc
            LEFT JOIN sis_marks_entries me
                ON me.component_id = mc.id AND me.student_id = ae.student_id
            WHERE ae.section_id   = :section_id
              AND ae.is_active    = true
              AND mc.section_id   = :section_id
              AND mc.is_active    = true
              AND mc.status       IN ('PUBLISHED', 'LOCKED')
              {course_filter}
            ORDER BY sp.usn NULLS LAST, u.full_name, mc.display_order NULLS LAST
        """)
        result = await db.execute(sql, params)
        return [dict(row) for row in result.mappings().all()]

    # ------------------------------------------------------------------
    # Analytics: student self-view
    # ------------------------------------------------------------------

    @staticmethod
    async def get_student_marks_raw(student_id: UUID, db: AsyncSession) -> list[dict]:
        """All PUBLISHED/LOCKED component marks for a student."""
        sql = text("""
            SELECT
                mc.id           AS component_id,
                mc.course_id,
                c.code          AS course_code,
                c.title         AS course_title,
                mc.section_id,
                s.name          AS section_name,
                mc.component_type,
                mc.name         AS component_name,
                mc.max_marks,
                mc.weightage,
                mc.due_date,
                mc.display_order,
                mc.status       AS component_status,
                me.marks_obtained,
                me.remarks
            FROM acad_enrollments  ae
            JOIN  acad_sections    s   ON s.id  = ae.section_id
            JOIN  sis_marks_components mc ON mc.section_id = ae.section_id
            LEFT JOIN courses      c   ON c.id  = mc.course_id
            LEFT JOIN sis_marks_entries me
                ON me.component_id = mc.id AND me.student_id = ae.student_id
            WHERE ae.student_id  = :student_id
              AND ae.is_active   = true
              AND mc.is_active   = true
              AND mc.status      IN ('PUBLISHED', 'LOCKED')
            ORDER BY mc.course_id, mc.display_order NULLS LAST, mc.created_at
        """)
        result = await db.execute(sql, {"student_id": str(student_id)})
        return [dict(row) for row in result.mappings().all()]

    # ------------------------------------------------------------------
    # Readiness: per-student eligibility pre-check
    # ------------------------------------------------------------------

    @staticmethod
    async def get_section_readiness_raw(
        section_id: UUID,
        attendance_threshold: float,
        db: AsyncSession,
    ) -> list[dict]:
        """
        For each enrolled student in the section, return:
          - attendance_pct (from finalized/LOCKED attendance sessions)
          - marks_filled (count of LOCKED components with entry for student)
          - marks_total_locked (count of LOCKED components for the section)
        """
        sql = text("""
            WITH enrolled AS (
                SELECT ae.student_id, u.full_name, sp.usn
                FROM acad_enrollments ae
                JOIN  users u ON u.id = ae.student_id
                LEFT JOIN sis_student_profiles sp ON sp.user_id = ae.student_id
                WHERE ae.section_id = :section_id AND ae.is_active = true
            ),
            locked_components AS (
                SELECT COUNT(*) AS total_locked
                FROM sis_marks_components
                WHERE section_id = :section_id AND status = 'LOCKED' AND is_active = true
            ),
            att_stats AS (
                SELECT
                    ar.student_id,
                    COUNT(CASE WHEN ar.status IN ('PRESENT','LATE') THEN 1 END) AS attended,
                    COUNT(CASE WHEN ar.status IN ('PRESENT','LATE','ABSENT') THEN 1 END) AS countable
                FROM sis_attendance_records ar
                JOIN sis_attendance_sessions ss ON ss.id = ar.session_id
                WHERE ss.section_id = :section_id AND ss.status = 'LOCKED'
                GROUP BY ar.student_id
            ),
            marks_fill AS (
                SELECT
                    me.student_id,
                    COUNT(me.id) AS filled_locked
                FROM sis_marks_entries me
                JOIN sis_marks_components mc ON mc.id = me.component_id
                WHERE mc.section_id = :section_id
                  AND mc.status = 'LOCKED'
                  AND me.marks_obtained IS NOT NULL
                GROUP BY me.student_id
            )
            SELECT
                e.student_id,
                e.full_name     AS student_name,
                e.usn,
                CASE WHEN att.countable > 0
                     THEN ROUND(att.attended::numeric / att.countable * 100, 2)
                     ELSE NULL
                END             AS attendance_pct,
                COALESCE(mf.filled_locked, 0) AS marks_filled,
                lc.total_locked
            FROM enrolled e
            CROSS JOIN locked_components lc
            LEFT JOIN att_stats  att ON att.student_id = e.student_id
            LEFT JOIN marks_fill mf  ON mf.student_id  = e.student_id
            ORDER BY e.usn NULLS LAST, e.full_name
        """)
        result = await db.execute(sql, {"section_id": str(section_id)})
        return [dict(row) for row in result.mappings().all()]

    # ------------------------------------------------------------------
    # Excel export helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def get_enrolled_with_entries(component_id: UUID, section_id: UUID, db: AsyncSession) -> list[dict]:
        """All enrolled students with their existing entry (if any) for a component."""
        sql = text("""
            SELECT
                ae.student_id,
                u.full_name,
                u.email,
                sp.usn,
                me.marks_obtained,
                me.remarks
            FROM acad_enrollments  ae
            JOIN  users            u   ON u.id  = ae.student_id AND u.is_active = true
            LEFT JOIN sis_student_profiles sp ON sp.user_id = ae.student_id
            LEFT JOIN sis_marks_entries me
                ON me.component_id = :component_id AND me.student_id = ae.student_id
            WHERE ae.section_id  = :section_id
              AND ae.is_active   = true
            ORDER BY sp.usn NULLS LAST, u.full_name
        """)
        result = await db.execute(sql, {
            "component_id": str(component_id),
            "section_id":   str(section_id),
        })
        return [dict(row) for row in result.mappings().all()]
