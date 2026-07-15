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
    TimetableSlotUpdate,
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
        SELECT c.code AS course_code, c.title AS course_title, u.full_name AS faculty_name,
               (c.is_elective OR c.elective_basket_id IS NOT NULL) AS is_elective
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
        room=slot.room, remarks=slot.remarks,
        is_elective=bool(row["is_elective"]) if row else False,
        start_time=start_time, end_time=end_time, period_label=period_label,
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
    async def _require_editable(timetable_id: UUID, verb: str, db: AsyncSession) -> Timetable:
        tt = await TimetableService.get(timetable_id, db)
        if tt is None:
            raise TimetableServiceError("TIMETABLE_NOT_FOUND", "Timetable not found.", 404)
        if tt.status not in (TimetableStatus.DRAFT.value, TimetableStatus.REJECTED.value):
            raise TimetableServiceError(
                "NOT_EDITABLE",
                f"Slots can only be {verb} while the timetable is DRAFT or REJECTED.", 409,
            )
        return tt

    @staticmethod
    async def _assert_no_slot_conflicts(
        tt: Timetable,
        *,
        day_of_week: int,
        period_number: int,
        faculty_user_id: UUID | None,
        room: str | None,
        db: AsyncSession,
        exclude_slot_ids: tuple[UUID, ...] = (),
    ) -> None:
        """The one place slot conflicts are decided.

        Three rules, unchanged from Phase 4.1: a day/period may hold at most one
        entry in this timetable; a faculty member may not teach two sections of
        the same semester at the same day/period; a room may not host two.

        `exclude_slot_ids` lets a slot be validated against its own new position
        without colliding with the row it is about to vacate — which is what
        makes move and swap possible. Every write path (add, update, swap) goes
        through here so the rules cannot drift apart.
        """
        occupied = select(TimetableSlot).where(
            TimetableSlot.timetable_id == tt.id,
            TimetableSlot.day_of_week == day_of_week,
            TimetableSlot.period_number == period_number,
        )
        if exclude_slot_ids:
            occupied = occupied.where(TimetableSlot.id.notin_(exclude_slot_ids))
        if (await db.execute(occupied)).scalar_one_or_none() is not None:
            raise TimetableServiceError(
                "SLOT_CONFLICT", "That day/period is already occupied in this timetable.", 409,
            )

        # Cross-timetable conflicts — scoped to the same semester, excluding this
        # timetable and REJECTED ones (moot slots).
        if faculty_user_id is not None:
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
                "faculty_id": str(faculty_user_id), "day": day_of_week, "period": period_number,
                "semester_id": str(tt.semester_id), "timetable_id": str(tt.id),
            })).mappings().first()
            if conflict is not None:
                raise TimetableServiceError(
                    "FACULTY_CONFLICT",
                    f"This faculty member is already teaching {conflict['section_name']} at this day/period.",
                    409,
                )

        if room:
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
                "room": room, "day": day_of_week, "period": period_number,
                "semester_id": str(tt.semester_id), "timetable_id": str(tt.id),
            })).mappings().first()
            if conflict is not None:
                raise TimetableServiceError(
                    "ROOM_CONFLICT",
                    f"Room '{room}' is already booked for {conflict['section_name']} at this day/period.",
                    409,
                )

    @staticmethod
    async def add_slot(timetable_id: UUID, body: TimetableSlotCreate, db: AsyncSession) -> TimetableSlot:
        tt = await TimetableService._require_editable(timetable_id, "added", db)
        await TimetableService._assert_no_slot_conflicts(
            tt, day_of_week=body.day_of_week, period_number=body.period_number,
            faculty_user_id=body.faculty_user_id, room=body.room, db=db,
        )

        slot = TimetableSlot(
            id=uuid.uuid4(), timetable_id=timetable_id, day_of_week=body.day_of_week,
            period_number=body.period_number, course_id=body.course_id,
            faculty_user_id=body.faculty_user_id, room=body.room, remarks=body.remarks,
        )
        db.add(slot)
        await db.commit()
        await db.refresh(slot)
        return slot

    @staticmethod
    async def update_slot(
        timetable_id: UUID, slot_id: UUID, body: TimetableSlotUpdate, db: AsyncSession,
    ) -> TimetableSlot:
        """Move a slot (day/period) or change its faculty, room or remarks.

        Validated against the slot's *target* position before anything is
        written, so a rejected move leaves the entry exactly where it was. The
        slot excludes itself from the occupancy check — otherwise moving a slot
        onto its own cell, or changing only its room, would collide with itself.
        """
        tt = await TimetableService._require_editable(timetable_id, "edited", db)
        slot = (await db.execute(select(TimetableSlot).where(
            TimetableSlot.id == slot_id, TimetableSlot.timetable_id == timetable_id,
        ))).scalar_one_or_none()
        if slot is None:
            raise TimetableServiceError("SLOT_NOT_FOUND", "Slot not found.", 404)

        updates = body.model_dump(exclude_unset=True)
        if not updates:
            raise TimetableServiceError("NO_FIELDS", "No fields to update.", 422)

        target_day     = updates.get("day_of_week",    slot.day_of_week)
        target_period  = updates.get("period_number",  slot.period_number)
        target_faculty = updates.get("faculty_user_id", slot.faculty_user_id)
        target_room    = updates.get("room",           slot.room)

        await TimetableService._assert_no_slot_conflicts(
            tt, day_of_week=target_day, period_number=target_period,
            faculty_user_id=target_faculty, room=target_room, db=db,
            exclude_slot_ids=(slot.id,),
        )

        for field, value in updates.items():
            setattr(slot, field, value)
        await db.commit()
        await db.refresh(slot)
        return slot

    @staticmethod
    async def swap_slots(
        timetable_id: UUID, slot_a_id: UUID, slot_b_id: UUID, db: AsyncSession,
    ) -> list[TimetableSlot]:
        """Exchange the day/period of two slots in the same timetable.

        `uq_timetable_slot_period` is an immediate constraint, so updating A onto
        B's cell collides before B has vacated it. The two rows are therefore
        deleted and re-inserted at each other's positions within one transaction.
        Slot ids are referenced by nothing else, so re-minting them is safe.

        Each slot is validated at its destination with BOTH originals excluded —
        they are the rows about to disappear.
        """
        if slot_a_id == slot_b_id:
            raise TimetableServiceError("INVALID_SWAP", "A slot cannot be swapped with itself.", 422)

        tt = await TimetableService._require_editable(timetable_id, "moved", db)
        slots = (await db.execute(select(TimetableSlot).where(
            TimetableSlot.timetable_id == timetable_id,
            TimetableSlot.id.in_((slot_a_id, slot_b_id)),
        ))).scalars().all()
        by_id = {s.id: s for s in slots}
        a, b = by_id.get(slot_a_id), by_id.get(slot_b_id)
        if a is None or b is None:
            raise TimetableServiceError("SLOT_NOT_FOUND", "Slot not found.", 404)

        both = (a.id, b.id)
        for moving, target in ((a, b), (b, a)):
            await TimetableService._assert_no_slot_conflicts(
                tt, day_of_week=target.day_of_week, period_number=target.period_number,
                faculty_user_id=moving.faculty_user_id, room=moving.room, db=db,
                exclude_slot_ids=both,
            )

        def _clone(src: TimetableSlot, at: TimetableSlot) -> TimetableSlot:
            return TimetableSlot(
                id=uuid.uuid4(), timetable_id=timetable_id,
                day_of_week=at.day_of_week, period_number=at.period_number,
                course_id=src.course_id, faculty_user_id=src.faculty_user_id,
                room=src.room, remarks=src.remarks,
            )

        new_a, new_b = _clone(a, b), _clone(b, a)
        await db.delete(a)
        await db.delete(b)
        await db.flush()   # vacate both cells before re-occupying them
        db.add_all([new_a, new_b])
        await db.commit()
        await db.refresh(new_a)
        await db.refresh(new_b)
        return [new_a, new_b]

    @staticmethod
    async def set_template(
        timetable_id: UUID, template_id: UUID | None, db: AsyncSession,
    ) -> Timetable:
        """Re-point a draft timetable at another schedule template.

        A template decides which period numbers exist and which are breaks. Swapping
        one in under existing slots can strand an entry on a period the new template
        does not teach — the slot survives in the database but never renders, and
        the Dean has no way to find it. So the swap is refused, naming the periods
        at fault, rather than quietly losing work.
        """
        tt = await TimetableService._require_editable(timetable_id, "re-templated", db)

        if template_id is not None:
            template = (await db.execute(select(TimetableTemplate).where(
                TimetableTemplate.id == template_id,
            ))).scalar_one_or_none()
            if template is None:
                raise TimetableServiceError("TEMPLATE_NOT_FOUND", "Template not found.", 404)

            taught = set((await db.execute(
                select(TimetablePeriod.period_number).where(
                    TimetablePeriod.template_id == template_id,
                    TimetablePeriod.period_type == "PERIOD",
                )
            )).scalars().all())
            used = set((await db.execute(
                select(TimetableSlot.period_number).where(TimetableSlot.timetable_id == timetable_id)
            )).scalars().all())
            stranded = sorted(used - taught)
            if stranded:
                periods = ", ".join(str(p) for p in stranded)
                raise TimetableServiceError(
                    "TEMPLATE_STRANDS_SLOTS",
                    f"This template does not teach period {periods}. "
                    f"Remove or move those entries before switching template.",
                    409,
                )

        tt.template_id = template_id
        tt.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(tt)
        return tt

    @staticmethod
    async def delete_timetable(timetable_id: UUID, db: AsyncSession) -> None:
        """Delete a timetable and, by FK cascade, its slots — nothing else.

        A PUBLISHED timetable is refused: students and faculty are reading it,
        and deleting it would silently empty their week. Unpublish is not a thing
        in this model, so the Dean must live with a published week until the next
        semester's timetable supersedes it.
        """
        tt = await TimetableService.get(timetable_id, db)
        if tt is None:
            raise TimetableServiceError("TIMETABLE_NOT_FOUND", "Timetable not found.", 404)
        if tt.status == TimetableStatus.PUBLISHED.value:
            raise TimetableServiceError(
                "CANNOT_DELETE_PUBLISHED",
                "A published timetable cannot be deleted — students and faculty are using it.",
                409,
            )
        await db.delete(tt)
        await db.commit()

    @staticmethod
    async def delete_slot(timetable_id: UUID, slot_id: UUID, db: AsyncSession) -> None:
        await TimetableService._require_editable(timetable_id, "removed", db)
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
    async def get_section_context(section_id: UUID, db: AsyncSession) -> dict:
        """Program name + code + batch years + semester label + section name for a
        section, so the timetable can be identified unambiguously as 'MCA
        (2026–2028) · Semester 1 · Section A' instead of a bare 'Section A'. The
        code and the batch years are what separate two live admissions of the same
        programme. Any piece may be None if the section's scheduling chain
        (section -> semester -> batch -> program) is incomplete."""
        row = (await db.execute(text("""
            SELECT sec.name AS section_name,
                   COALESCE(sem.label, 'Semester ' || sem.number) AS semester_label,
                   ap.name AS program_name,
                   ap.code AS program_code,
                   ab.name AS batch_name,
                   CASE WHEN ab.start_year IS NOT NULL
                        THEN ab.start_year || '–' || ab.end_year END AS academic_year
            FROM acad_sections sec
            LEFT JOIN acad_semesters sem ON sem.id = sec.semester_id
            LEFT JOIN acad_batches   ab  ON ab.id = sem.batch_id
            LEFT JOIN acad_programs  ap  ON ap.id = ab.program_id
            WHERE sec.id = :id
        """), {"id": str(section_id)})).mappings().first()
        if row is None:
            return {
                "section_name": None, "semester_label": None, "program_name": None,
                "program_code": None, "batch_name": None, "academic_year": None,
            }
        return dict(row)

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
        ctx = await TimetableService.get_section_context(scope["section_id"], db)
        return {
            "section_id": scope["section_id"], "section_name": scope["section_name"],
            "semester_label": ctx["semester_label"], "program_name": ctx["program_name"],
            "academic_year": ctx.get("academic_year"),
            "slots": slots, "template": template,
        }

    @staticmethod
    async def get_faculty_timetable(faculty_id: UUID, db: AsyncSession) -> list[FacultyTimetableSlotOut]:
        """All PUBLISHED slots across any section/semester where this faculty teaches."""
        rows = (await db.execute(text("""
            SELECT ts.id, ts.day_of_week, ts.period_number, ts.course_id, ts.faculty_user_id, ts.room,
                   ts.remarks,
                   c.code AS course_code, c.title AS course_title,
                   (c.is_elective OR c.elective_basket_id IS NOT NULL) AS is_elective,
                   sec.name AS section_name,
                   COALESCE(sem.label, 'Semester ' || sem.number) AS semester_name,
                   ap.name AS program_name,
                   tp.start_time, tp.end_time, tp.label AS period_label
            FROM timetable_slots ts
            JOIN timetables tt ON tt.id = ts.timetable_id AND tt.status = 'PUBLISHED'
            JOIN courses c ON c.id = ts.course_id
            JOIN acad_sections sec ON sec.id = tt.section_id
            JOIN acad_semesters sem ON sem.id = tt.semester_id
            LEFT JOIN acad_batches  ab ON ab.id = sem.batch_id
            LEFT JOIN acad_programs ap ON ap.id = ab.program_id
            LEFT JOIN timetable_periods tp ON tp.template_id = tt.template_id AND tp.period_number = ts.period_number
            WHERE ts.faculty_user_id = :faculty_id
            ORDER BY ts.day_of_week, ts.period_number
        """), {"faculty_id": str(faculty_id)})).mappings().all()
        return [
            FacultyTimetableSlotOut(
                id=r["id"], day_of_week=r["day_of_week"], period_number=r["period_number"],
                course_id=r["course_id"], course_code=r["course_code"], course_title=r["course_title"],
                faculty_user_id=r["faculty_user_id"], faculty_name=None, room=r["room"],
                remarks=r["remarks"], is_elective=bool(r["is_elective"]),
                start_time=r["start_time"], end_time=r["end_time"], period_label=r["period_label"],
                section_name=r["section_name"], semester_name=r["semester_name"],
                program_name=r["program_name"],
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
    async def delete_template(template_id: UUID, db: AsyncSession) -> None:
        """Delete a template and its periods (CASCADE). Any timetable linked to
        it keeps working — the FK is ON DELETE SET NULL, so those timetables
        simply revert to the default period grid."""
        tpl = await TimetableService.get_template(template_id, db)
        if tpl is None:
            raise TimetableServiceError("NOT_FOUND", "Template not found.", 404)
        await db.delete(tpl)
        await db.commit()

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
