from __future__ import annotations

import uuid
from datetime import datetime, time
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timetable.models import (
    Timetable,
    TimetablePeriod,
    TimetableSlot,
    TimetableStatus,
    TimetableTemplate,
)
from app.core.timetable.schemas import (
    FacultyTimetableSlotOut,
    TimetablePeriodCreate,
    TimetablePeriodOut,
    TimetableSlotCreate,
    TimetableSlotOut,
    TimetableTemplateOut,
)


class TimetableServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def _resolve_period_time(
    timetable_id: UUID, period_number: int, db: AsyncSession
) -> tuple[time | None, time | None, str | None]:
    """Resolve a slot's real start/end time + break-style label from the
    timetable's linked template, if any — null triple for pre-Phase-4.1
    timetables with no template."""
    row = (await db.execute(text("""
        SELECT tp.start_time, tp.end_time, tp.label
        FROM timetables tt
        JOIN timetable_periods tp ON tp.template_id = tt.template_id AND tp.period_number = :period_number
        WHERE tt.id = :timetable_id AND tt.template_id IS NOT NULL
    """), {"timetable_id": str(timetable_id), "period_number": period_number})).mappings().first()
    if row is None:
        return None, None, None
    return row["start_time"], row["end_time"], row["label"]


async def _slot_out(slot: TimetableSlot, db: AsyncSession) -> TimetableSlotOut:
    row = (await db.execute(text("""
        SELECT c.code AS course_code, c.title AS course_title, u.full_name AS faculty_name
        FROM courses c
        LEFT JOIN users u ON u.id = :faculty_user_id
        WHERE c.id = :course_id
    """), {"course_id": str(slot.course_id), "faculty_user_id": str(slot.faculty_user_id) if slot.faculty_user_id else None})).mappings().first()
    start_time, end_time, period_label = await _resolve_period_time(slot.timetable_id, slot.period_number, db)
    return TimetableSlotOut(
        id=slot.id, day_of_week=slot.day_of_week, period_number=slot.period_number,
        course_id=slot.course_id, course_code=row["course_code"] if row else None,
        course_title=row["course_title"] if row else None,
        faculty_user_id=slot.faculty_user_id, faculty_name=row["faculty_name"] if row else None,
        room=slot.room, start_time=start_time, end_time=end_time, period_label=period_label,
    )


class TimetableService:
    @staticmethod
    async def create(
        section_id: UUID, semester_id: UUID, created_by: UUID, db: AsyncSession,
        template_id: UUID | None = None,
    ) -> Timetable:
        existing = (await db.execute(
            select(Timetable).where(Timetable.section_id == section_id, Timetable.semester_id == semester_id)
        )).scalar_one_or_none()
        if existing is not None:
            raise TimetableServiceError(
                "TIMETABLE_EXISTS",
                "A timetable already exists for this section and semester. Edit the existing one instead.",
                409,
            )
        if template_id is not None:
            from app.core.timetable.dean_scope import get_section_department_id

            tpl = await TimetableService.get_template(template_id, db)
            if tpl is None:
                raise TimetableServiceError("TEMPLATE_NOT_FOUND", "Template not found.", 404)
            section_department_id = await get_section_department_id(section_id, db)
            if section_department_id is None or tpl.department_id != section_department_id:
                raise TimetableServiceError(
                    "TEMPLATE_DEPARTMENT_MISMATCH",
                    "This template belongs to a different department than the selected section.",
                    400,
                )
        tt = Timetable(
            id=uuid.uuid4(), section_id=section_id, semester_id=semester_id,
            status=TimetableStatus.DRAFT.value, created_by_user_id=created_by,
            template_id=template_id,
        )
        db.add(tt)
        await db.commit()
        await db.refresh(tt)
        return tt

    @staticmethod
    async def get(timetable_id: UUID, db: AsyncSession) -> Timetable | None:
        return (await db.execute(select(Timetable).where(Timetable.id == timetable_id))).scalar_one_or_none()

    @staticmethod
    async def list(
        db: AsyncSession, section_id: UUID | None = None, semester_id: UUID | None = None, status: str | None = None,
        section_ids: list[UUID] | None = None,
    ) -> list[Timetable]:
        stmt = select(Timetable)
        if section_id is not None:
            stmt = stmt.where(Timetable.section_id == section_id)
        if semester_id is not None:
            stmt = stmt.where(Timetable.semester_id == semester_id)
        if status is not None:
            stmt = stmt.where(Timetable.status == status)
        if section_ids is not None:
            if not section_ids:
                return []
            stmt = stmt.where(Timetable.section_id.in_(section_ids))
        stmt = stmt.order_by(Timetable.created_at.desc())
        return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def list_slots(timetable_id: UUID, db: AsyncSession) -> list[TimetableSlot]:
        stmt = select(TimetableSlot).where(TimetableSlot.timetable_id == timetable_id).order_by(
            TimetableSlot.day_of_week, TimetableSlot.period_number
        )
        return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def slots_out(timetable_id: UUID, db: AsyncSession) -> list[TimetableSlotOut]:
        slots = await TimetableService.list_slots(timetable_id, db)
        return [await _slot_out(s, db) for s in slots]

    @staticmethod
    async def slot_out(slot: TimetableSlot, db: AsyncSession) -> TimetableSlotOut:
        return await _slot_out(slot, db)

    @staticmethod
    async def add_slot(timetable_id: UUID, body: TimetableSlotCreate, db: AsyncSession) -> TimetableSlot:
        tt = await TimetableService.get(timetable_id, db)
        if tt is None:
            raise TimetableServiceError("TIMETABLE_NOT_FOUND", "Timetable not found.", 404)
        if tt.status not in (TimetableStatus.DRAFT.value, TimetableStatus.REJECTED.value):
            raise TimetableServiceError(
                "NOT_EDITABLE", "Slots can only be added while the timetable is DRAFT or REJECTED.", 409,
            )
        existing = (await db.execute(select(TimetableSlot).where(
            TimetableSlot.timetable_id == timetable_id,
            TimetableSlot.day_of_week == body.day_of_week,
            TimetableSlot.period_number == body.period_number,
        ))).scalar_one_or_none()
        if existing is not None:
            raise TimetableServiceError("SLOT_CONFLICT", "That day/period is already occupied in this timetable.", 409)

        # Cross-timetable conflict validation (Phase 4.1) — scoped to the same
        # semester, excluding this timetable and REJECTED ones (moot slots).
        if body.faculty_user_id is not None:
            conflict = (await db.execute(text("""
                SELECT sec.name AS section_name
                FROM timetable_slots ts2
                JOIN timetables tt2    ON tt2.id = ts2.timetable_id
                JOIN acad_sections sec ON sec.id = tt2.section_id
                WHERE ts2.faculty_user_id = :faculty_id
                  AND ts2.day_of_week = :day
                  AND ts2.period_number = :period
                  AND tt2.semester_id = :semester_id
                  AND tt2.status != 'REJECTED'
                  AND tt2.id != :timetable_id
                LIMIT 1
            """), {
                "faculty_id": str(body.faculty_user_id), "day": body.day_of_week, "period": body.period_number,
                "semester_id": str(tt.semester_id), "timetable_id": str(timetable_id),
            })).mappings().first()
            if conflict is not None:
                raise TimetableServiceError(
                    "FACULTY_CONFLICT",
                    f"This faculty member is already teaching {conflict['section_name']} at this day/period.",
                    409,
                )

        if body.room:
            conflict = (await db.execute(text("""
                SELECT sec.name AS section_name
                FROM timetable_slots ts2
                JOIN timetables tt2    ON tt2.id = ts2.timetable_id
                JOIN acad_sections sec ON sec.id = tt2.section_id
                WHERE ts2.room = :room
                  AND ts2.day_of_week = :day
                  AND ts2.period_number = :period
                  AND tt2.semester_id = :semester_id
                  AND tt2.status != 'REJECTED'
                  AND tt2.id != :timetable_id
                LIMIT 1
            """), {
                "room": body.room, "day": body.day_of_week, "period": body.period_number,
                "semester_id": str(tt.semester_id), "timetable_id": str(timetable_id),
            })).mappings().first()
            if conflict is not None:
                raise TimetableServiceError(
                    "ROOM_CONFLICT",
                    f"Room '{body.room}' is already booked for {conflict['section_name']} at this day/period.",
                    409,
                )

        slot = TimetableSlot(
            id=uuid.uuid4(), timetable_id=timetable_id, day_of_week=body.day_of_week,
            period_number=body.period_number, course_id=body.course_id,
            faculty_user_id=body.faculty_user_id, room=body.room,
        )
        db.add(slot)
        await db.commit()
        await db.refresh(slot)
        return slot

    @staticmethod
    async def delete_slot(timetable_id: UUID, slot_id: UUID, db: AsyncSession) -> None:
        tt = await TimetableService.get(timetable_id, db)
        if tt is None:
            raise TimetableServiceError("TIMETABLE_NOT_FOUND", "Timetable not found.", 404)
        if tt.status not in (TimetableStatus.DRAFT.value, TimetableStatus.REJECTED.value):
            raise TimetableServiceError(
                "NOT_EDITABLE", "Slots can only be removed while the timetable is DRAFT or REJECTED.", 409,
            )
        slot = (await db.execute(select(TimetableSlot).where(
            TimetableSlot.id == slot_id, TimetableSlot.timetable_id == timetable_id,
        ))).scalar_one_or_none()
        if slot is None:
            raise TimetableServiceError("SLOT_NOT_FOUND", "Slot not found.", 404)
        await db.delete(slot)
        await db.commit()

    @staticmethod
    async def submit(timetable_id: UUID, db: AsyncSession) -> Timetable:
        tt = await TimetableService.get(timetable_id, db)
        if tt is None:
            raise TimetableServiceError("TIMETABLE_NOT_FOUND", "Timetable not found.", 404)
        if tt.status not in (TimetableStatus.DRAFT.value, TimetableStatus.REJECTED.value):
            raise TimetableServiceError("INVALID_STATUS", "Only DRAFT or REJECTED timetables can be submitted.", 409)
        tt.status = TimetableStatus.PENDING_REVIEW.value
        tt.submitted_at = datetime.utcnow()
        tt.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(tt)
        return tt

    @staticmethod
    async def approve(timetable_id: UUID, reviewer_id: UUID, db: AsyncSession) -> Timetable:
        tt = await TimetableService.get(timetable_id, db)
        if tt is None:
            raise TimetableServiceError("TIMETABLE_NOT_FOUND", "Timetable not found.", 404)
        if tt.status != TimetableStatus.PENDING_REVIEW.value:
            raise TimetableServiceError("INVALID_STATUS", "Only PENDING_REVIEW timetables can be approved.", 409)
        tt.status = TimetableStatus.APPROVED.value
        tt.reviewed_by_user_id = reviewer_id
        tt.reviewed_at = datetime.utcnow()
        tt.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(tt)
        return tt

    @staticmethod
    async def reject(timetable_id: UUID, reviewer_id: UUID, comment: str, db: AsyncSession) -> Timetable:
        tt = await TimetableService.get(timetable_id, db)
        if tt is None:
            raise TimetableServiceError("TIMETABLE_NOT_FOUND", "Timetable not found.", 404)
        if tt.status != TimetableStatus.PENDING_REVIEW.value:
            raise TimetableServiceError("INVALID_STATUS", "Only PENDING_REVIEW timetables can be rejected.", 409)
        tt.status = TimetableStatus.REJECTED.value
        tt.reviewed_by_user_id = reviewer_id
        tt.reviewed_at = datetime.utcnow()
        tt.review_comment = comment
        tt.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(tt)
        return tt

    @staticmethod
    async def publish(timetable_id: UUID, publisher_id: UUID, db: AsyncSession) -> Timetable:
        tt = await TimetableService.get(timetable_id, db)
        if tt is None:
            raise TimetableServiceError("TIMETABLE_NOT_FOUND", "Timetable not found.", 404)
        if tt.status != TimetableStatus.APPROVED.value:
            raise TimetableServiceError("INVALID_STATUS", "Only APPROVED timetables can be published.", 409)
        tt.status = TimetableStatus.PUBLISHED.value
        tt.published_by_user_id = publisher_id
        tt.published_at = datetime.utcnow()
        tt.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(tt)
        return tt

    @staticmethod
    async def get_section_name(section_id: UUID, db: AsyncSession) -> str | None:
        row = (await db.execute(text("SELECT name FROM acad_sections WHERE id = :id"), {"id": str(section_id)})).mappings().first()
        return row["name"] if row else None

    @staticmethod
    async def get_student_timetable(student_id: UUID, db: AsyncSession) -> dict | None:
        """PUBLISHED timetable for the student's current section, or None if not yet published."""
        scope = (await db.execute(text("""
            SELECT s.id AS section_id, s.name AS section_name, s.semester_id
            FROM acad_enrollments ae
            JOIN acad_sections s ON s.id = ae.section_id
            WHERE ae.student_id = :student_id AND ae.is_active = true
        """), {"student_id": str(student_id)})).mappings().first()
        if scope is None:
            return None
        tt = (await db.execute(select(Timetable).where(
            Timetable.section_id == scope["section_id"],
            Timetable.semester_id == scope["semester_id"],
            Timetable.status == TimetableStatus.PUBLISHED.value,
        ))).scalar_one_or_none()
        if tt is None:
            return None
        slots = await TimetableService.slots_out(tt.id, db)
        template = await TimetableService.get_template_full(tt.template_id, db)
        return {
            "section_id": scope["section_id"], "section_name": scope["section_name"],
            "slots": slots, "template": template,
        }

    @staticmethod
    async def get_faculty_timetable(faculty_id: UUID, db: AsyncSession) -> list[FacultyTimetableSlotOut]:
        """All PUBLISHED slots across any section/semester where this faculty teaches."""
        rows = (await db.execute(text("""
            SELECT ts.id, ts.day_of_week, ts.period_number, ts.course_id, ts.faculty_user_id, ts.room,
                   c.code AS course_code, c.title AS course_title,
                   sec.name AS section_name,
                   COALESCE(sem.label, 'Semester ' || sem.number) AS semester_name,
                   tp.start_time, tp.end_time, tp.label AS period_label
            FROM timetable_slots ts
            JOIN timetables tt ON tt.id = ts.timetable_id AND tt.status = 'PUBLISHED'
            JOIN courses c ON c.id = ts.course_id
            JOIN acad_sections sec ON sec.id = tt.section_id
            JOIN acad_semesters sem ON sem.id = tt.semester_id
            LEFT JOIN timetable_periods tp ON tp.template_id = tt.template_id AND tp.period_number = ts.period_number
            WHERE ts.faculty_user_id = :faculty_id
            ORDER BY ts.day_of_week, ts.period_number
        """), {"faculty_id": str(faculty_id)})).mappings().all()
        return [
            FacultyTimetableSlotOut(
                id=r["id"], day_of_week=r["day_of_week"], period_number=r["period_number"],
                course_id=r["course_id"], course_code=r["course_code"], course_title=r["course_title"],
                faculty_user_id=r["faculty_user_id"], faculty_name=None, room=r["room"],
                start_time=r["start_time"], end_time=r["end_time"], period_label=r["period_label"],
                section_name=r["section_name"], semester_name=r["semester_name"],
            )
            for r in rows
        ]

    # -----------------------------------------------------------------------
    # Timetable Template / Period (Phase 4.1)
    # -----------------------------------------------------------------------

    @staticmethod
    async def create_template(
        department_id: UUID, name: str, working_days: list[int], saturday_mode: str | None,
        college_start_time: time, college_end_time: time, created_by: UUID, db: AsyncSession,
    ) -> TimetableTemplate:
        tpl = TimetableTemplate(
            id=uuid.uuid4(), department_id=department_id, name=name, working_days=working_days,
            saturday_mode=saturday_mode, college_start_time=college_start_time,
            college_end_time=college_end_time, created_by_user_id=created_by,
        )
        db.add(tpl)
        await db.commit()
        await db.refresh(tpl)
        return tpl

    @staticmethod
    async def get_template(template_id: UUID, db: AsyncSession) -> TimetableTemplate | None:
        return (await db.execute(
            select(TimetableTemplate).where(TimetableTemplate.id == template_id)
        )).scalar_one_or_none()

    @staticmethod
    async def list_templates(department_ids: list[UUID], db: AsyncSession) -> list[TimetableTemplate]:
        if not department_ids:
            return []
        stmt = select(TimetableTemplate).where(
            TimetableTemplate.department_id.in_(department_ids)
        ).order_by(TimetableTemplate.created_at.desc())
        return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def update_template(template_id: UUID, updates: dict, db: AsyncSession) -> TimetableTemplate:
        tpl = await TimetableService.get_template(template_id, db)
        if tpl is None:
            raise TimetableServiceError("NOT_FOUND", "Template not found.", 404)
        for k, v in updates.items():
            if v is not None:
                setattr(tpl, k, v)
        tpl.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(tpl)
        return tpl

    @staticmethod
    async def list_periods(template_id: UUID, db: AsyncSession) -> list[TimetablePeriod]:
        stmt = select(TimetablePeriod).where(
            TimetablePeriod.template_id == template_id
        ).order_by(TimetablePeriod.sequence_number)
        return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def add_period(template_id: UUID, body: TimetablePeriodCreate, db: AsyncSession) -> TimetablePeriod:
        if body.period_type == "PERIOD" and body.period_number is None:
            raise TimetableServiceError("VALIDATION_ERROR", "period_number is required for PERIOD rows.", 400)
        if body.period_type == "BREAK" and body.period_number is not None:
            raise TimetableServiceError("VALIDATION_ERROR", "period_number must be omitted for BREAK rows.", 400)
        if body.period_type == "PERIOD":
            existing = (await db.execute(select(TimetablePeriod).where(
                TimetablePeriod.template_id == template_id,
                TimetablePeriod.period_number == body.period_number,
            ))).scalar_one_or_none()
            if existing is not None:
                raise TimetableServiceError(
                    "PERIOD_NUMBER_CONFLICT", f"Period {body.period_number} already exists in this template.", 409,
                )
        period = TimetablePeriod(
            id=uuid.uuid4(), template_id=template_id, sequence_number=body.sequence_number,
            period_type=body.period_type, period_number=body.period_number, label=body.label,
            start_time=body.start_time, end_time=body.end_time, skip_on_half_day=body.skip_on_half_day,
        )
        db.add(period)
        await db.commit()
        await db.refresh(period)
        return period

    @staticmethod
    async def get_period(period_id: UUID, db: AsyncSession) -> TimetablePeriod | None:
        return (await db.execute(
            select(TimetablePeriod).where(TimetablePeriod.id == period_id)
        )).scalar_one_or_none()

    @staticmethod
    async def update_period(period_id: UUID, updates: dict, db: AsyncSession) -> TimetablePeriod:
        period = await TimetableService.get_period(period_id, db)
        if period is None:
            raise TimetableServiceError("NOT_FOUND", "Period not found.", 404)
        for k, v in updates.items():
            if v is not None:
                setattr(period, k, v)
        await db.commit()
        await db.refresh(period)
        return period

    @staticmethod
    async def delete_period(period_id: UUID, db: AsyncSession) -> None:
        period = await TimetableService.get_period(period_id, db)
        if period is None:
            raise TimetableServiceError("NOT_FOUND", "Period not found.", 404)
        await db.delete(period)
        await db.commit()

    @staticmethod
    async def get_template_full(template_id: UUID | None, db: AsyncSession) -> TimetableTemplateOut | None:
        """Canonical template-with-periods-and-department-name builder — reused
        by both the router's TimetableOut embed and get_student_timetable()."""
        if template_id is None:
            return None
        tpl = await TimetableService.get_template(template_id, db)
        if tpl is None:
            return None
        dept_row = (await db.execute(
            text("SELECT name FROM acad_departments WHERE id = :id"), {"id": str(tpl.department_id)}
        )).mappings().first()
        periods = await TimetableService.list_periods(template_id, db)
        return TimetableTemplateOut(
            id=tpl.id, department_id=tpl.department_id,
            department_name=dept_row["name"] if dept_row else None,
            name=tpl.name, working_days=tpl.working_days, saturday_mode=tpl.saturday_mode,
            college_start_time=tpl.college_start_time, college_end_time=tpl.college_end_time,
            periods=[TimetablePeriodOut.model_validate(p) for p in periods],
            created_by_user_id=tpl.created_by_user_id, created_at=tpl.created_at, updated_at=tpl.updated_at,
        )
