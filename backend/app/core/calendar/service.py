from __future__ import annotations

import uuid
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.calendar.models import (
    AcademicEvent,
    AcademicEventType,
    AcademicEventVisibility,
)
from app.core.calendar.schemas import (
    AcademicEventCreate,
    AcademicEventUpdate,
    CalendarItem,
)


class CalendarServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def _get_student_scope(student_id: UUID, db: AsyncSession) -> dict | None:
    """Resolve the student's current section/semester/batch/program for
    calendar-visibility scoping. One active enrollment per student."""
    sql = text("""
        SELECT s.id AS section_id, sem.id AS semester_id,
               b.id AS batch_id, p.id AS program_id
        FROM acad_enrollments ae
        JOIN acad_sections s   ON s.id = ae.section_id
        JOIN acad_semesters sem ON sem.id = s.semester_id
        JOIN acad_batches b     ON b.id = sem.batch_id
        JOIN acad_programs p    ON p.id = b.program_id
        WHERE ae.student_id = :student_id AND ae.is_active = true
    """)
    row = (await db.execute(sql, {"student_id": str(student_id)})).mappings().first()
    return dict(row) if row else None


class CalendarService:
    @staticmethod
    async def get_student_calendar(
        student_id: UUID, date_from: date, date_to: date, db: AsyncSession
    ) -> list[CalendarItem]:
        items: list[CalendarItem] = []
        scope = await _get_student_scope(student_id, db)

        # 1. Declared events & holidays visible to this student, plus their own
        #    PERSONAL events — a student's private note lives in the same table,
        #    seen only by whoever created it.
        event_sql = text("""
            SELECT id, title, description, event_type, start_at, end_at,
                   is_all_day, visibility, created_by_user_id
            FROM academic_events
            WHERE start_at::date BETWEEN :date_from AND :date_to
              AND (
                    visibility = 'ALL'
                    OR (visibility = 'PROGRAM'  AND program_id = :program_id)
                    OR (visibility = 'BATCH'    AND batch_id   = :batch_id)
                    OR (visibility = 'SECTION'  AND section_id = :section_id)
                    OR (visibility = 'PERSONAL' AND created_by_user_id = :student_id)
              )
            ORDER BY start_at
        """)
        rows = (await db.execute(event_sql, {
            "date_from": date_from, "date_to": date_to,
            "student_id": str(student_id),
            "program_id": str(scope["program_id"]) if scope else None,
            "batch_id":   str(scope["batch_id"])   if scope else None,
            "section_id": str(scope["section_id"]) if scope else None,
        })).mappings().all()
        for r in rows:
            start_at: datetime = r["start_at"]
            end_at: datetime | None = r["end_at"]
            items.append(CalendarItem(
                id=str(r["id"]),
                title=r["title"],
                detail=r["description"],
                item_type=r["event_type"],
                date=start_at.date(),
                start_time=None if r["is_all_day"] else start_at.time(),
                end_time=None if (r["is_all_day"] or end_at is None) else end_at.time(),
                all_day=r["is_all_day"],
                source_module="calendar",
                link=None,
                # The student may remove their own note; nothing else here is theirs
                # to delete.
                editable=r["visibility"] == "PERSONAL",
            ))

        # 2. Assignment due dates (m04_assignments — new module, WRITTEN coursework)
        assignment_sql = text("""
            SELECT a.id, a.title, a.due_date, a.syllabus_id, c.code AS course_code
            FROM assignments a
            JOIN syllabi syl ON syl.id = a.syllabus_id
            LEFT JOIN courses c ON c.id = syl.course_id
            JOIN acad_enrollments ae ON ae.student_id = :student_id AND ae.is_active = true
            JOIN acad_sections s ON s.id = ae.section_id
            JOIN subject_assignments sa
              ON sa.is_active = true
             AND sa.course_id = syl.course_id
             AND (sa.section_id = ae.section_id OR (sa.section_id IS NULL AND sa.semester_id = s.semester_id))
            WHERE a.due_date::date BETWEEN :date_from AND :date_to
              AND a.status = 'PUBLISHED'
        """)
        try:
            rows = (await db.execute(assignment_sql, {
                "student_id": str(student_id), "date_from": date_from, "date_to": date_to,
            })).mappings().all()
        except Exception:
            rows = []  # tolerate assignments table not existing yet during rollout
        for r in rows:
            due: datetime = r["due_date"]
            items.append(CalendarItem(
                id=str(r["id"]), title=r["title"],
                detail=r["course_code"],
                item_type="ASSIGNMENT_DUE", date=due.date(), start_time=due.time(),
                end_time=None, all_day=False, source_module="assignments",
                link=f"/student/assignments/{r['id']}",
            ))

        # 3. Lab deadlines (m06_labs_evaluator — unchanged, existing module)
        lab_sql = text("""
            SELECT la.id, la.title, la.deadline, c.code AS course_code
            FROM lab_assignments la
            JOIN syllabi syl ON syl.id = la.syllabus_id
            LEFT JOIN courses c ON c.id = syl.course_id
            JOIN acad_enrollments ae ON ae.student_id = :student_id AND ae.is_active = true
            JOIN acad_sections s ON s.id = ae.section_id
            JOIN subject_assignments sa
              ON sa.is_active = true
             AND sa.course_id = syl.course_id
             AND (sa.section_id = ae.section_id OR (sa.section_id IS NULL AND sa.semester_id = s.semester_id))
            WHERE la.deadline::date BETWEEN :date_from AND :date_to
              AND la.status = 'PUBLISHED'
        """)
        rows = (await db.execute(lab_sql, {
            "student_id": str(student_id), "date_from": date_from, "date_to": date_to,
        })).mappings().all()
        for r in rows:
            due: datetime = r["deadline"]
            items.append(CalendarItem(
                id=str(r["id"]), title=r["title"],
                detail=r["course_code"],
                item_type="LAB_DUE", date=due.date(), start_time=due.time(),
                end_time=None, all_day=False, source_module="labs",
                link=f"/student/labs/{r['id']}",
            ))

        # 4. Exam schedule (m11_sis) — only from a session the student can see.
        #    A DRAFT session is the department still working; putting it on a
        #    student's calendar would announce a date nobody has committed to.
        exam_sql = text("""
            SELECT sch.course_id, c.title AS course_title, c.code AS course_code,
                   sch.exam_date, sch.start_time, sch.end_time, sch.room_number,
                   ses.session_name, ses.session_type
            FROM sis_exam_schedules sch
            JOIN sis_exam_sessions ses ON ses.id = sch.session_id
            JOIN courses c ON c.id = sch.course_id
            JOIN acad_enrollments ae ON ae.student_id = :student_id AND ae.is_active = true
            WHERE sch.section_id = ae.section_id
              AND sch.exam_date BETWEEN :date_from AND :date_to
              AND ses.status <> 'DRAFT'
        """)
        rows = (await db.execute(exam_sql, {
            "student_id": str(student_id), "date_from": date_from, "date_to": date_to,
        })).mappings().all()
        for r in rows:
            detail = " · ".join(x for x in (
                r["course_code"], r["session_name"],
                f"Room {r['room_number']}" if r["room_number"] else None,
            ) if x)
            items.append(CalendarItem(
                id=f"exam-{r['course_id']}-{r['exam_date']}",
                title=r["course_title"],
                detail=detail or None,
                item_type="EXAM", date=r["exam_date"], start_time=r["start_time"],
                end_time=r["end_time"], all_day=r["start_time"] is None, source_module="exam",
                link="/sis/exam/my-timetable",
            ))

        # 5. Research viva sessions
        viva_sql = text("""
            SELECT id, scheduled_at, expires_at
            FROM viva_sessions
            WHERE student_user_id = :student_id
              AND scheduled_at IS NOT NULL
              AND scheduled_at::date BETWEEN :date_from AND :date_to
        """)
        rows = (await db.execute(viva_sql, {
            "student_id": str(student_id), "date_from": date_from, "date_to": date_to,
        })).mappings().all()
        for r in rows:
            sched: datetime = r["scheduled_at"]
            items.append(CalendarItem(
                id=str(r["id"]), title="Research Viva",
                item_type="VIVA", date=sched.date(), start_time=sched.time(),
                end_time=None, all_day=False, source_module="research",
                link=f"/student/viva/{r['id']}",
            ))

        items.sort(key=lambda i: (i.date, i.start_time or datetime.min.time()))
        return items

    @staticmethod
    async def get_teaching_days(student_id: UUID, db: AsyncSession) -> list[int]:
        """The weekdays this student's section actually has class on.

        There is no universal rule for Saturday — some institutions teach on it,
        some do not — so the only honest source is the student's own PUBLISHED
        timetable. A student with no timetable yet gets Monday-Friday, the common
        case, rather than an empty week that would grey out the whole calendar.
        """
        scope = await _get_student_scope(student_id, db)
        if not scope:
            return [0, 1, 2, 3, 4]

        rows = (await db.execute(
            text("""
                SELECT DISTINCT s.day_of_week
                FROM timetable_slots s
                JOIN timetables t ON t.id = s.timetable_id
                WHERE t.section_id = :section_id
                  AND t.status = 'PUBLISHED'
                ORDER BY s.day_of_week
            """),
            {"section_id": str(scope["section_id"])},
        )).scalars().all()

        return [int(d) for d in rows] if rows else [0, 1, 2, 3, 4]

    @staticmethod
    async def create_personal_event(
        body: AcademicEventCreate, student_id: UUID, db: AsyncSession
    ) -> AcademicEvent:
        """A student's own note on their own calendar.

        Forced to PERSONAL on both axes: a student may add something to their own
        calendar and nobody else's, so neither the visibility nor the audience
        columns are theirs to choose.
        """
        ev = AcademicEvent(
            id=uuid.uuid4(),
            title=body.title, description=body.description,
            event_type=AcademicEventType.PERSONAL.value,
            start_at=body.start_at, end_at=body.end_at,
            is_all_day=body.is_all_day,
            visibility=AcademicEventVisibility.PERSONAL.value,
            program_id=None, batch_id=None, section_id=None,
            created_by_user_id=student_id,
        )
        db.add(ev)
        await db.commit()
        await db.refresh(ev)
        return ev

    @staticmethod
    async def delete_personal_event(
        event_id: UUID, student_id: UUID, db: AsyncSession
    ) -> None:
        """Remove one's own note. Anything else — a holiday, an exam — is not the
        student's to delete, and reads as not-found rather than forbidden so the
        endpoint cannot be used to probe for events they cannot see."""
        from sqlalchemy import select

        ev = (await db.execute(
            select(AcademicEvent).where(
                AcademicEvent.id == event_id,
                AcademicEvent.visibility == AcademicEventVisibility.PERSONAL.value,
                AcademicEvent.created_by_user_id == student_id,
            )
        )).scalar_one_or_none()
        if ev is None:
            raise CalendarServiceError(
                "EVENT_NOT_FOUND", "Personal event not found.", 404
            )
        await db.delete(ev)
        await db.commit()

    @staticmethod
    async def create_event(body: AcademicEventCreate, created_by: UUID, db: AsyncSession) -> AcademicEvent:
        ev = AcademicEvent(
            id=uuid.uuid4(),
            title=body.title, description=body.description,
            event_type=body.event_type.value, start_at=body.start_at, end_at=body.end_at,
            is_all_day=body.is_all_day, visibility=body.visibility.value,
            program_id=body.program_id, batch_id=body.batch_id, section_id=body.section_id,
            created_by_user_id=created_by,
        )
        db.add(ev)
        await db.commit()
        await db.refresh(ev)
        return ev

    @staticmethod
    async def list_events(db: AsyncSession) -> list[AcademicEvent]:
        from sqlalchemy import select
        rows = (await db.execute(select(AcademicEvent).order_by(AcademicEvent.start_at))).scalars().all()
        return list(rows)

    @staticmethod
    async def update_event(event_id: UUID, body: AcademicEventUpdate, db: AsyncSession) -> AcademicEvent:
        from sqlalchemy import select
        ev = (await db.execute(select(AcademicEvent).where(AcademicEvent.id == event_id))).scalar_one_or_none()
        if ev is None:
            raise CalendarServiceError("EVENT_NOT_FOUND", "Calendar event not found.", 404)
        data = body.model_dump(exclude_unset=True)
        for field, value in data.items():
            if field in ("event_type", "visibility") and value is not None:
                value = value.value if hasattr(value, "value") else value
            setattr(ev, field, value)
        ev.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(ev)
        return ev

    @staticmethod
    async def delete_event(event_id: UUID, db: AsyncSession) -> None:
        from sqlalchemy import select
        ev = (await db.execute(select(AcademicEvent).where(AcademicEvent.id == event_id))).scalar_one_or_none()
        if ev is None:
            raise CalendarServiceError("EVENT_NOT_FOUND", "Calendar event not found.", 404)
        await db.delete(ev)
        await db.commit()
