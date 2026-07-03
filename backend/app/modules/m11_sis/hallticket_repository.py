"""
SIS Hall Ticket Eligibility — H58 Repository.

All DB operations for sis_hall_ticket_eligibility and sis_hall_ticket_batches.

Engine SQL computes eligibility for every student in a semester in one pass:
  - attendance_pct: aggregate PRESENT / (PRESENT+ABSENT) across all courses
    for the student's section, finalized (LOCKED) sessions only.
  - has_shortage: TRUE if any single course attendance_pct < threshold_pct
    (same per-course logic as H56 shortage detection)
  - marks_all_locked: TRUE if all active sis_marks_components for the section
    have status=LOCKED (or there are no components → treated as N/A = pass)
  - marks_all_filled: TRUE if every LOCKED component has marks_obtained IS NOT NULL
    for this student (or no LOCKED components → N/A = pass)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m11_sis.hallticket_models import (
    SisHallTicketBatch, SisHallTicketEligibility,
)


class HallTicketRepository:

    # ------------------------------------------------------------------
    # Engine — compute eligibility for all students in a semester
    # ------------------------------------------------------------------

    @staticmethod
    async def compute_eligibility_rows(
        *,
        semester_id:   UUID,
        section_id:    Optional[UUID],
        threshold_pct: float,
        db:            AsyncSession,
    ) -> list[dict]:
        """
        Returns one dict per enrolled student with all check values.

        Does NOT write to DB — service layer decides what to upsert.
        """
        section_filter = "AND sec.id = :section_id" if section_id else ""
        params: dict = {
            "semester_id":   str(semester_id),
            "threshold_pct": threshold_pct,
        }
        if section_id:
            params["section_id"] = str(section_id)

        sql = text(f"""
            WITH enrolled AS (
                -- One active enrollment per student; join to get section + semester
                SELECT
                    e.student_id,
                    e.section_id,
                    sec.semester_id,
                    u.full_name    AS student_name,
                    u.email        AS email,
                    sp.usn         AS usn
                FROM acad_enrollments e
                JOIN acad_sections    sec ON sec.id = e.section_id
                JOIN users            u   ON u.id   = e.student_id
                LEFT JOIN sis_student_profiles sp ON sp.user_id = e.student_id
                WHERE sec.semester_id = :semester_id
                  AND e.is_active      = true
                  {section_filter}
            ),

            -- ── Attendance per course per student ─────────────────────────
            att_per_course AS (
                SELECT
                    ar.student_id,
                    sess.section_id,
                    sess.course_id,
                    COUNT(CASE WHEN ar.status = 'PRESENT' THEN 1 END) AS attended,
                    COUNT(*)                                          AS total_countable
                FROM sis_attendance_sessions sess
                JOIN sis_attendance_records   ar   ON ar.session_id = sess.id
                JOIN enrolled                 enr  ON enr.student_id = ar.student_id
                                                  AND enr.section_id = sess.section_id
                WHERE sess.status = 'LOCKED'
                GROUP BY ar.student_id, sess.section_id, sess.course_id
            ),

            -- ── Aggregate attendance across all courses per student ────────
            att_agg AS (
                SELECT
                    student_id,
                    section_id,
                    SUM(attended)       AS total_attended,
                    SUM(total_countable) AS total_countable,
                    CASE
                        WHEN SUM(total_countable) > 0
                        THEN ROUND(SUM(attended)::numeric / SUM(total_countable) * 100, 2)
                        ELSE NULL
                    END AS attendance_pct,
                    -- shortage: TRUE if any course falls below threshold
                    BOOL_OR(
                        CASE
                            WHEN total_countable > 0
                            THEN (attended::numeric / total_countable * 100) < :threshold_pct
                            ELSE FALSE
                        END
                    ) AS has_shortage,
                    COUNT(*) > 0 AS has_att_data
                FROM att_per_course
                GROUP BY student_id, section_id
            ),

            -- ── Marks per course per student ──────────────────────────────
            marks_per_course AS (
                SELECT
                    enr.student_id,
                    mc.section_id,
                    mc.course_id,
                    COUNT(mc.id)                                                    AS total_components,
                    COUNT(CASE WHEN mc.status = 'LOCKED' THEN 1 END)               AS locked_count,
                    COUNT(CASE WHEN mc.status != 'LOCKED' THEN 1 END)              AS unlocked_count,
                    COUNT(CASE WHEN mc.status = 'LOCKED'
                               AND me.marks_obtained IS NOT NULL THEN 1 END)        AS filled_locked_count
                FROM enrolled enr
                JOIN sis_marks_components mc ON mc.section_id = enr.section_id
                                             AND mc.is_active = true
                LEFT JOIN sis_marks_entries me ON me.component_id = mc.id
                                               AND me.student_id  = enr.student_id
                GROUP BY enr.student_id, mc.section_id, mc.course_id
            ),

            -- ── Aggregate marks across all courses per student ────────────
            marks_agg AS (
                SELECT
                    student_id,
                    section_id,
                    COUNT(*) > 0 AS has_marks_data,
                    -- all_locked: every course has zero unlocked components
                    BOOL_AND(unlocked_count = 0)                          AS marks_all_locked,
                    -- all_filled: for each course, locked_count = 0 OR filled = locked
                    BOOL_AND(locked_count = 0 OR filled_locked_count = locked_count) AS marks_all_filled
                FROM marks_per_course
                GROUP BY student_id, section_id
            ),

            -- ── Semester metadata for snapshot ────────────────────────────
            sem_meta AS (
                SELECT
                    sem.id                 AS semester_id,
                    sem.number             AS sem_number,
                    COALESCE(sem.label, 'Semester ' || sem.number) AS sem_label,
                    b.start_year,
                    b.end_year
                FROM acad_semesters sem
                JOIN acad_batches   b  ON b.id = sem.batch_id
                WHERE sem.id = :semester_id
            )

            SELECT
                enr.student_id,
                enr.section_id,
                enr.semester_id,
                enr.student_name,
                enr.email,
                enr.usn,

                -- attendance
                COALESCE(aa.attendance_pct,  NULL)          AS attendance_pct,
                COALESCE(aa.has_shortage,    false)         AS has_shortage,
                COALESCE(aa.has_att_data,    false)         AS has_att_data,

                -- marks
                COALESCE(ma.marks_all_locked, true)         AS marks_all_locked,
                COALESCE(ma.marks_all_filled, true)         AS marks_all_filled,
                COALESCE(ma.has_marks_data,   false)        AS has_marks_data,

                -- snapshot metadata
                sm.sem_label                                AS computed_semester_name,
                (sm.start_year::text || '-' || sm.end_year::text) AS computed_academic_year,
                sm.sem_number                               AS sem_number,
                sm.end_year                                 AS batch_end_year

            FROM enrolled enr
            CROSS JOIN sem_meta sm
            LEFT JOIN att_agg   aa ON aa.student_id = enr.student_id
                                   AND aa.section_id = enr.section_id
            LEFT JOIN marks_agg ma ON ma.student_id = enr.student_id
                                   AND ma.section_id = enr.section_id
            ORDER BY enr.student_name
        """)

        result = await db.execute(sql, params)
        return [dict(row) for row in result.mappings().all()]

    # ------------------------------------------------------------------
    # Upsert — engine result → DB row
    # ------------------------------------------------------------------

    @staticmethod
    async def upsert_eligibility(row: SisHallTicketEligibility, db: AsyncSession) -> SisHallTicketEligibility:
        """
        INSERT ... ON CONFLICT DO UPDATE — preserves override fields if already overridden.
        Uses raw SQL so we can apply conditional update logic.
        """
        sql = text("""
            INSERT INTO sis_hall_ticket_eligibility (
                id, student_id, semester_id, publish_status, status,
                computed_at, attendance_threshold_used,
                computed_academic_year, computed_semester_name,
                attendance_pct, has_shortage, marks_all_locked, marks_all_filled,
                failure_reasons, created_at, updated_at
            ) VALUES (
                :id, :student_id, :semester_id, :publish_status, :status,
                :computed_at, :threshold,
                :academic_year, :semester_name,
                :att_pct, :has_shortage, :marks_locked, :marks_filled,
                :failure_reasons, now(), now()
            )
            ON CONFLICT (student_id, semester_id) DO UPDATE SET
                -- Only update if NOT already overridden + PUBLISHED (protect human decisions)
                status                    = CASE
                    WHEN sis_hall_ticket_eligibility.override_by IS NOT NULL
                     AND sis_hall_ticket_eligibility.publish_status = 'PUBLISHED'
                    THEN sis_hall_ticket_eligibility.status
                    ELSE EXCLUDED.status
                  END,
                publish_status            = CASE
                    WHEN sis_hall_ticket_eligibility.publish_status = 'PUBLISHED'
                    THEN 'PUBLISHED'
                    ELSE 'DRAFT'
                  END,
                computed_at               = EXCLUDED.computed_at,
                attendance_threshold_used = EXCLUDED.attendance_threshold_used,
                computed_academic_year    = EXCLUDED.computed_academic_year,
                computed_semester_name    = EXCLUDED.computed_semester_name,
                attendance_pct            = EXCLUDED.attendance_pct,
                has_shortage              = EXCLUDED.has_shortage,
                marks_all_locked          = EXCLUDED.marks_all_locked,
                marks_all_filled          = EXCLUDED.marks_all_filled,
                failure_reasons           = EXCLUDED.failure_reasons,
                updated_at                = now()
            RETURNING *
        """)

        reasons = row.failure_reasons or []
        result = await db.execute(sql, {
            "id":             str(row.id),
            "student_id":     str(row.student_id),
            "semester_id":    str(row.semester_id),
            "publish_status": row.publish_status,
            "status":         row.status,
            "computed_at":    row.computed_at,
            "threshold":      row.attendance_threshold_used,
            "academic_year":  row.computed_academic_year,
            "semester_name":  row.computed_semester_name,
            "att_pct":        row.attendance_pct,
            "has_shortage":   row.has_shortage,
            "marks_locked":   row.marks_all_locked,
            "marks_filled":   row.marks_all_filled,
            "failure_reasons": reasons,
        })
        await db.flush()
        return row

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(eligibility_id: UUID, db: AsyncSession) -> Optional[SisHallTicketEligibility]:
        return (
            await db.execute(
                select(SisHallTicketEligibility).where(
                    SisHallTicketEligibility.id == eligibility_id
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    async def get_by_student_semester(
        student_id: UUID, semester_id: UUID, db: AsyncSession
    ) -> Optional[SisHallTicketEligibility]:
        return (
            await db.execute(
                select(SisHallTicketEligibility).where(
                    SisHallTicketEligibility.student_id  == student_id,
                    SisHallTicketEligibility.semester_id == semester_id,
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    async def list_by_semester(
        *,
        semester_id:    UUID,
        section_id:     Optional[UUID]  = None,
        status:         Optional[str]   = None,
        publish_status: Optional[str]   = None,
        has_shortage:   Optional[bool]  = None,
        db:             AsyncSession,
    ) -> list[dict]:
        """
        Returns enriched rows (student name, USN, email) for a semester.
        """
        filters = ["ht.semester_id = :semester_id"]
        params: dict = {"semester_id": str(semester_id)}

        if status:
            filters.append("ht.status = :status")
            params["status"] = status
        if publish_status:
            filters.append("ht.publish_status = :publish_status")
            params["publish_status"] = publish_status
        if has_shortage is not None:
            filters.append("ht.has_shortage = :has_shortage")
            params["has_shortage"] = has_shortage
        if section_id:
            # need to join via enrollment
            filters.append("""
                ht.student_id IN (
                    SELECT e.student_id FROM acad_enrollments e
                    JOIN acad_sections sec ON sec.id = e.section_id
                    WHERE sec.id = :section_id AND e.is_active = true
                )
            """)
            params["section_id"] = str(section_id)

        where = " AND ".join(filters)
        sql = text(f"""
            SELECT
                ht.*,
                u.full_name  AS student_name,
                u.email      AS email,
                sp.usn       AS usn
            FROM sis_hall_ticket_eligibility ht
            JOIN users u ON u.id = ht.student_id
            LEFT JOIN sis_student_profiles sp ON sp.user_id = ht.student_id
            WHERE {where}
            ORDER BY u.full_name
        """)
        result = await db.execute(sql, params)
        return [dict(row) for row in result.mappings().all()]

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    @staticmethod
    async def publish_semester(
        *, semester_id: UUID, section_id: Optional[UUID], db: AsyncSession
    ) -> int:
        """Moves all DRAFT rows for the semester to PUBLISHED. Returns count."""
        section_sub = ""
        params: dict = {"semester_id": str(semester_id)}

        if section_id:
            section_sub = """
                AND ht.student_id IN (
                    SELECT e.student_id FROM acad_enrollments e
                    JOIN acad_sections sec ON sec.id = e.section_id
                    WHERE sec.id = :section_id AND e.is_active = true
                )
            """
            params["section_id"] = str(section_id)

        sql = text(f"""
            UPDATE sis_hall_ticket_eligibility ht
            SET    publish_status = 'PUBLISHED',
                   updated_at     = now()
            WHERE  ht.semester_id    = :semester_id
              AND  ht.publish_status = 'DRAFT'
              {section_sub}
        """)
        result = await db.execute(sql, params)
        await db.flush()
        return result.rowcount

    # ------------------------------------------------------------------
    # Override
    # ------------------------------------------------------------------

    @staticmethod
    async def apply_override(
        row: SisHallTicketEligibility,
        *,
        actor_id:       UUID,
        new_status:     str,
        reason:         str,
        db:             AsyncSession,
    ) -> SisHallTicketEligibility:
        now = datetime.now(timezone.utc)
        row.override_by     = actor_id
        row.override_at     = now
        row.override_reason = reason
        row.override_status = new_status
        row.status          = new_status
        row.updated_at      = now
        await db.flush()
        await db.refresh(row)
        return row

    # ------------------------------------------------------------------
    # Batches — create
    # ------------------------------------------------------------------

    @staticmethod
    async def create_batch(batch: SisHallTicketBatch, db: AsyncSession) -> SisHallTicketBatch:
        db.add(batch)
        await db.flush()
        await db.refresh(batch)
        return batch

    @staticmethod
    async def get_batch_by_id(batch_id: UUID, db: AsyncSession) -> Optional[SisHallTicketBatch]:
        return (
            await db.execute(
                select(SisHallTicketBatch).where(SisHallTicketBatch.id == batch_id)
            )
        ).scalar_one_or_none()

    @staticmethod
    async def list_batches(semester_id: Optional[UUID], db: AsyncSession) -> list[SisHallTicketBatch]:
        q = select(SisHallTicketBatch)
        if semester_id:
            q = q.where(SisHallTicketBatch.semester_id == semester_id)
        q = q.order_by(SisHallTicketBatch.generated_at.desc())
        return list((await db.execute(q)).scalars().all())

    # ------------------------------------------------------------------
    # Assign hall ticket numbers for a batch
    # ------------------------------------------------------------------

    @staticmethod
    async def assign_hall_tickets(
        *,
        semester_id:   UUID,
        section_id:    Optional[UUID],
        batch_id:      UUID,
        ticket_prefix: str,
        db:            AsyncSession,
    ) -> int:
        """
        Assigns hall_ticket_number to all PUBLISHED ELIGIBLE/CONDITIONAL rows
        that don't yet have a number.  Format: {prefix}-{USN} or {prefix}-{seq:04d}.
        Returns count of tickets assigned.
        """
        section_sub = ""
        params: dict = {
            "semester_id":    str(semester_id),
            "batch_id":       str(batch_id),
            "ticket_prefix":  ticket_prefix,
        }

        if section_id:
            section_sub = """
                AND ht.student_id IN (
                    SELECT e.student_id FROM acad_enrollments e
                    JOIN acad_sections sec ON sec.id = e.section_id
                    WHERE sec.id = :section_id AND e.is_active = true
                )
            """
            params["section_id"] = str(section_id)

        sql = text(f"""
            WITH eligible AS (
                SELECT
                    ht.id,
                    ht.student_id,
                    COALESCE(sp.usn, LPAD(
                        ROW_NUMBER() OVER (ORDER BY u.full_name)::text,
                        4, '0'
                    )) AS ticket_suffix
                FROM sis_hall_ticket_eligibility ht
                JOIN users u ON u.id = ht.student_id
                LEFT JOIN sis_student_profiles sp ON sp.user_id = ht.student_id
                WHERE ht.semester_id    = :semester_id
                  AND ht.publish_status = 'PUBLISHED'
                  AND ht.status IN ('ELIGIBLE', 'CONDITIONAL')
                  AND ht.hall_ticket_number IS NULL
                  {section_sub}
            )
            UPDATE sis_hall_ticket_eligibility ht
            SET    batch_id           = :batch_id ::uuid,
                   hall_ticket_number = :ticket_prefix || '-' || e.ticket_suffix,
                   updated_at         = now()
            FROM eligible e
            WHERE ht.id = e.id
        """)
        result = await db.execute(sql, params)
        await db.flush()
        return result.rowcount

    # ------------------------------------------------------------------
    # Count helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def count_publishable(
        *, semester_id: UUID, section_id: Optional[UUID], db: AsyncSession
    ) -> dict:
        """
        Returns counts of PUBLISHED ELIGIBLE/CONDITIONAL rows available
        for batch generation (hall_ticket_number IS NULL).
        """
        section_sub = ""
        params: dict = {"semester_id": str(semester_id)}
        if section_id:
            section_sub = """
                AND ht.student_id IN (
                    SELECT e.student_id FROM acad_enrollments e
                    JOIN acad_sections sec ON sec.id = e.section_id
                    WHERE sec.id = :section_id AND e.is_active = true
                )
            """
            params["section_id"] = str(section_id)

        sql = text(f"""
            SELECT
                COUNT(*) FILTER (WHERE ht.status = 'ELIGIBLE')    AS eligible,
                COUNT(*) FILTER (WHERE ht.status = 'CONDITIONAL') AS conditional,
                COUNT(*) FILTER (WHERE ht.status = 'NOT_ELIGIBLE') AS not_eligible
            FROM sis_hall_ticket_eligibility ht
            WHERE ht.semester_id    = :semester_id
              AND ht.publish_status = 'PUBLISHED'
              AND ht.hall_ticket_number IS NULL
              {section_sub}
        """)
        result = await db.execute(sql, params)
        row = dict(result.mappings().one())
        return row

    # ------------------------------------------------------------------
    # Semester metadata helper
    # ------------------------------------------------------------------

    @staticmethod
    async def get_semester_meta(semester_id: UUID, db: AsyncSession) -> Optional[dict]:
        sql = text("""
            SELECT
                sem.id,
                sem.number,
                COALESCE(sem.label, 'Semester ' || sem.number) AS label,
                b.start_year,
                b.end_year
            FROM acad_semesters sem
            JOIN acad_batches   b  ON b.id = sem.batch_id
            WHERE sem.id = :semester_id
        """)
        result = await db.execute(sql, {"semester_id": str(semester_id)})
        row = result.mappings().one_or_none()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Faculty advisory — section-scoped enriched rows
    # ------------------------------------------------------------------

    @staticmethod
    async def list_advisory_for_faculty(
        *, section_id: UUID, semester_id: UUID, db: AsyncSession
    ) -> list[dict]:
        sql = text("""
            SELECT
                e.student_id,
                u.full_name    AS student_name,
                sp.usn         AS usn,
                ht.attendance_pct,
                ht.has_shortage,
                ht.marks_all_locked,
                ht.marks_all_filled,
                ht.status,
                ht.publish_status
            FROM acad_enrollments e
            JOIN users u ON u.id = e.student_id
            LEFT JOIN sis_student_profiles sp ON sp.user_id = e.student_id
            LEFT JOIN sis_hall_ticket_eligibility ht
                   ON ht.student_id  = e.student_id
                  AND ht.semester_id = :semester_id
            JOIN acad_sections sec ON sec.id = e.section_id
            WHERE sec.id       = :section_id
              AND e.is_active  = true
            ORDER BY u.full_name
        """)
        result = await db.execute(sql, {
            "section_id":  str(section_id),
            "semester_id": str(semester_id),
        })
        return [dict(row) for row in result.mappings().all()]
