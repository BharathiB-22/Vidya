"""
SIS Examination Management — H59 Service.

Business rules:
  - ADMIN and DEAN manage all exam resources (sessions, schedules, centers,
    invigilation, seat allocation).
  - FACULTY sees only their own invigilation assignments.
  - STUDENT sees only PUBLISHED+ sessions; their timetable; their hall ticket.
  - Session lifecycle: DRAFT → PUBLISHED → SEATING_ALLOCATED → LOCKED → COMPLETED.
    No backwards transitions.
  - Schedules editable only in DRAFT/PUBLISHED; blocked after SEATING_ALLOCATED.
  - Session deletable only in DRAFT status and only if no schedules exist.
  - Seat allocation requires: session PUBLISHED (or SEATING_ALLOCATED for re-run),
    active center, total room capacity >= eligible students.
  - After seat allocation, session transitions to SEATING_ALLOCATED and
    hall_ticket_generated_at/by are stamped on the session.
  - NOT_ELIGIBLE students are hard-blocked from receiving seats.
  - All lifecycle transitions are audit-logged.
  - AI advises, humans decide — no autonomous grade or rejection logic here.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.modules.m11_sis.exam_models import ExamSessionStatus
from app.modules.m11_sis.exam_repository import (
    ExamCenterRepository,
    ExamInvigilationRepository,
    ExamScheduleRepository,
    ExamSeatingRepository,
    ExamSessionRepository,
    ExamStudentRepository,
)
from app.modules.m11_sis.exam_schemas import (
    CourseScheduleRow,
    ExamCenterCreateIn,
    ExamCenterOut,
    ExamCenterUpdateIn,
    ExamScheduleCreateIn,
    ExamScheduleOut,
    ExamScheduleUpdateIn,
    ExamSessionCreateIn,
    ExamSessionOut,
    ExamSessionUpdateIn,
    InvigilationCreateIn,
    InvigilationOut,
    MyHallTicketExamOut,
    RoomAllocationDetail,
    RoomSpec,
    SeatAllocationIn,
    SeatingAllocationResult,
    SeatInfo,
    StudentSeatOut,
    StudentTimetableOut,
)

logger = logging.getLogger("vidya.sis.exam")

# Statuses visible to students and faculty
_PUBLIC_STATUSES = (
    ExamSessionStatus.PUBLISHED,
    ExamSessionStatus.SEATING_ALLOCATED,
    ExamSessionStatus.LOCKED,
    ExamSessionStatus.COMPLETED,
)

# Statuses in which schedule edits are allowed
_EDITABLE_STATUSES = (ExamSessionStatus.DRAFT, ExamSessionStatus.PUBLISHED)


# ─────────────────────────────────────────────────────────────────────────────
# Service error
# ─────────────────────────────────────────────────────────────────────────────

class ExamServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code


def _not_found(entity: str) -> ExamServiceError:
    return ExamServiceError(f"{entity}_NOT_FOUND", f"{entity} not found.", 404)


# ─────────────────────────────────────────────────────────────────────────────
# Exam Center Service
# ─────────────────────────────────────────────────────────────────────────────

class ExamCenterService:

    @staticmethod
    async def create(
        body: ExamCenterCreateIn, *, actor_user_id: UUID, actor_role: str,
        tenant_id: UUID, schema_name: str, db: AsyncSession,
    ) -> ExamCenterOut:
        center = await ExamCenterRepository.create(db, body.model_dump())
        await AuditService.log(
            db,
            event_type=AuditEventType.EXAM_SEATS_ALLOCATED,  # reuse closest event
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SisExamCenter",
            target_id=str(center.id),
            metadata_={"action": "create_center", "center_code": center.center_code},
        )
        return ExamCenterOut.model_validate(center)

    @staticmethod
    async def get(center_id: UUID, db: AsyncSession) -> ExamCenterOut:
        center = await ExamCenterRepository.get(db, center_id)
        if center is None:
            raise _not_found("CENTER")
        return ExamCenterOut.model_validate(center)

    @staticmethod
    async def list_all(db: AsyncSession, include_inactive: bool = False) -> list[ExamCenterOut]:
        centers = await ExamCenterRepository.list_all(db, include_inactive)
        return [ExamCenterOut.model_validate(c) for c in centers]

    @staticmethod
    async def update(
        center_id: UUID, body: ExamCenterUpdateIn,
        *, actor_user_id: UUID, actor_role: str,
        tenant_id: UUID, schema_name: str, db: AsyncSession,
    ) -> ExamCenterOut:
        updates = body.model_dump(exclude_none=True)
        center = await ExamCenterRepository.update(db, center_id, updates)
        if center is None:
            raise _not_found("CENTER")
        return ExamCenterOut.model_validate(center)


# ─────────────────────────────────────────────────────────────────────────────
# Exam Session Service
# ─────────────────────────────────────────────────────────────────────────────

class ExamSessionService:

    @staticmethod
    async def create(
        body: ExamSessionCreateIn,
        *, actor_user_id: UUID, actor_role: str,
        tenant_id: UUID, schema_name: str, db: AsyncSession,
    ) -> ExamSessionOut:
        data = body.model_dump()
        data["created_by"] = actor_user_id
        session = await ExamSessionRepository.create(db, data)
        return ExamSessionService._enrich_out(
            {**_orm_to_dict(session), "schedule_count": 0}
        )

    @staticmethod
    async def get(session_id: UUID, db: AsyncSession, is_manager: bool = True) -> ExamSessionOut:
        session = await ExamSessionRepository.get(db, session_id)
        if session is None:
            raise _not_found("SESSION")
        if not is_manager and session.status == ExamSessionStatus.DRAFT:
            raise ExamServiceError("SESSION_NOT_FOUND", "Session not found.", 404)
        count = await ExamSessionRepository.count_schedules(db, session_id)
        return ExamSessionService._enrich_out({**_orm_to_dict(session), "schedule_count": count})

    @staticmethod
    async def list_sessions(
        db: AsyncSession,
        semester_id: Optional[UUID] = None,
        status_filter: Optional[str] = None,
        session_type_filter: Optional[str] = None,
        is_manager: bool = True,
    ) -> list[ExamSessionOut]:
        visible = None if is_manager else tuple(s.value for s in _PUBLIC_STATUSES)
        rows = await ExamSessionRepository.list_for_semester(
            db,
            semester_id=semester_id,
            status_filter=status_filter,
            session_type_filter=session_type_filter,
            visible_statuses=visible,
        )
        return [ExamSessionService._enrich_out(r) for r in rows]

    @staticmethod
    async def update(
        session_id: UUID, body: ExamSessionUpdateIn,
        *, actor_user_id: UUID, actor_role: str,
        tenant_id: UUID, schema_name: str, db: AsyncSession,
    ) -> ExamSessionOut:
        session = await ExamSessionRepository.get(db, session_id)
        if session is None:
            raise _not_found("SESSION")
        if session.status != ExamSessionStatus.DRAFT:
            raise ExamServiceError(
                "INVALID_SESSION_STATUS",
                "Only DRAFT sessions can be edited directly. "
                "Use lifecycle transitions to progress the session.",
            )
        updates = body.model_dump(exclude_none=True)
        session = await ExamSessionRepository.update(db, session_id, updates)
        count = await ExamSessionRepository.count_schedules(db, session_id)
        return ExamSessionService._enrich_out({**_orm_to_dict(session), "schedule_count": count})

    @staticmethod
    async def delete(
        session_id: UUID,
        *, actor_user_id: UUID, actor_role: str,
        tenant_id: UUID, schema_name: str, db: AsyncSession,
    ) -> None:
        session = await ExamSessionRepository.get(db, session_id)
        if session is None:
            raise _not_found("SESSION")
        if session.status != ExamSessionStatus.DRAFT:
            raise ExamServiceError(
                "SESSION_NOT_DELETABLE",
                "Only DRAFT sessions can be deleted.",
            )
        count = await ExamSessionRepository.count_schedules(db, session_id)
        if count > 0:
            raise ExamServiceError(
                "SESSION_HAS_SCHEDULES",
                f"Cannot delete session with {count} schedule(s). Remove schedules first.",
            )
        await ExamSessionRepository.delete(db, session_id)

    @staticmethod
    async def publish(
        session_id: UUID,
        *, actor_user_id: UUID, actor_role: str,
        tenant_id: UUID, schema_name: str, db: AsyncSession,
    ) -> ExamSessionOut:
        return await ExamSessionService._transition(
            session_id,
            from_status=ExamSessionStatus.DRAFT,
            to_status=ExamSessionStatus.PUBLISHED,
            audit_event=AuditEventType.EXAM_SESSION_PUBLISHED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            db=db,
        )

    @staticmethod
    async def lock(
        session_id: UUID,
        *, actor_user_id: UUID, actor_role: str,
        tenant_id: UUID, schema_name: str, db: AsyncSession,
    ) -> ExamSessionOut:
        return await ExamSessionService._transition(
            session_id,
            from_status=ExamSessionStatus.SEATING_ALLOCATED,
            to_status=ExamSessionStatus.LOCKED,
            audit_event=AuditEventType.EXAM_SESSION_LOCKED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            db=db,
        )

    @staticmethod
    async def complete(
        session_id: UUID,
        *, actor_user_id: UUID, actor_role: str,
        tenant_id: UUID, schema_name: str, db: AsyncSession,
    ) -> ExamSessionOut:
        return await ExamSessionService._transition(
            session_id,
            from_status=ExamSessionStatus.LOCKED,
            to_status=ExamSessionStatus.COMPLETED,
            audit_event=AuditEventType.EXAM_SESSION_COMPLETED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            db=db,
        )

    @staticmethod
    async def _transition(
        session_id: UUID,
        *, from_status: str, to_status: str,
        audit_event: AuditEventType,
        actor_user_id: UUID, actor_role: str,
        tenant_id: UUID, schema_name: str, db: AsyncSession,
    ) -> ExamSessionOut:
        session = await ExamSessionRepository.get(db, session_id)
        if session is None:
            raise _not_found("SESSION")
        if session.status != from_status:
            raise ExamServiceError(
                "INVALID_SESSION_STATUS",
                f"Session must be in {from_status} status to transition to {to_status}. "
                f"Current status: {session.status}.",
            )
        session = await ExamSessionRepository.update(
            db, session_id, {"status": to_status}
        )
        await AuditService.log(
            db,
            event_type=audit_event,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SisExamSession",
            target_id=str(session_id),
            metadata_={"session_name": session.session_name, "new_status": to_status},
        )
        count = await ExamSessionRepository.count_schedules(db, session_id)
        return ExamSessionService._enrich_out({**_orm_to_dict(session), "schedule_count": count})

    @staticmethod
    def _enrich_out(row: dict) -> ExamSessionOut:
        return ExamSessionOut.model_validate(row)


# ─────────────────────────────────────────────────────────────────────────────
# Exam Schedule Service
# ─────────────────────────────────────────────────────────────────────────────

class ExamScheduleService:

    @staticmethod
    async def create(
        session_id: UUID, body: ExamScheduleCreateIn,
        *, actor_user_id: UUID, actor_role: str,
        tenant_id: UUID, schema_name: str, db: AsyncSession,
    ) -> ExamScheduleOut:
        session = await ExamSessionRepository.get(db, session_id)
        if session is None:
            raise _not_found("SESSION")
        if session.status not in _EDITABLE_STATUSES:
            raise ExamServiceError(
                "SCHEDULE_NOT_EDITABLE",
                f"Schedules cannot be added when session is {session.status}.",
            )
        duplicate = await ExamScheduleRepository.check_duplicate(
            db, session_id, body.course_id, body.section_id
        )
        if duplicate:
            raise ExamServiceError(
                "SCHEDULE_DUPLICATE",
                "A schedule for this course and section already exists in this session.",
                409,
            )
        data = body.model_dump()
        data["session_id"] = session_id
        data["created_by"] = actor_user_id
        schedule = await ExamScheduleRepository.create(db, data)
        rows = await ExamScheduleRepository.list_for_session(db, session_id)
        row = next((r for r in rows if str(r["id"]) == str(schedule.id)), None)
        if row is None:
            raise ExamServiceError("SCHEDULE_NOT_FOUND", "Schedule created but not found.", 500)
        return ExamScheduleOut.model_validate(row)

    @staticmethod
    async def list_schedules(
        db: AsyncSession,
        session_id: UUID,
        section_id: Optional[UUID] = None,
        is_manager: bool = True,
    ) -> list[ExamScheduleOut]:
        session = await ExamSessionRepository.get(db, session_id)
        if session is None:
            raise _not_found("SESSION")
        if not is_manager and session.status == ExamSessionStatus.DRAFT:
            raise ExamServiceError("SESSION_NOT_FOUND", "Session not found.", 404)
        rows = await ExamScheduleRepository.list_for_session(db, session_id, section_id)
        return [ExamScheduleOut.model_validate(r) for r in rows]

    @staticmethod
    async def update(
        schedule_id: UUID, body: ExamScheduleUpdateIn,
        *, actor_user_id: UUID, actor_role: str,
        tenant_id: UUID, schema_name: str, db: AsyncSession,
    ) -> ExamScheduleOut:
        schedule = await ExamScheduleRepository.get(db, schedule_id)
        if schedule is None:
            raise _not_found("SCHEDULE")
        session = await ExamSessionRepository.get(db, schedule.session_id)
        if session is None:
            raise _not_found("SESSION")
        if session.status not in _EDITABLE_STATUSES:
            raise ExamServiceError(
                "SCHEDULE_NOT_EDITABLE",
                f"Schedules cannot be edited when session is {session.status}.",
            )
        updates = body.model_dump(exclude_none=True)
        await ExamScheduleRepository.update(db, schedule_id, updates)
        rows = await ExamScheduleRepository.list_for_session(db, schedule.session_id)
        row = next((r for r in rows if str(r["id"]) == str(schedule_id)), None)
        if row is None:
            raise ExamServiceError("SCHEDULE_NOT_FOUND", "Schedule not found after update.", 500)
        return ExamScheduleOut.model_validate(row)

    @staticmethod
    async def delete(
        schedule_id: UUID,
        *, actor_user_id: UUID, actor_role: str,
        tenant_id: UUID, schema_name: str, db: AsyncSession,
    ) -> None:
        schedule = await ExamScheduleRepository.get(db, schedule_id)
        if schedule is None:
            raise _not_found("SCHEDULE")
        session = await ExamSessionRepository.get(db, schedule.session_id)
        if session is None:
            raise _not_found("SESSION")
        if session.status != ExamSessionStatus.DRAFT:
            raise ExamServiceError(
                "SCHEDULE_NOT_EDITABLE",
                "Schedules can only be deleted when the session is in DRAFT status.",
            )
        await ExamScheduleRepository.delete(db, schedule_id)


# ─────────────────────────────────────────────────────────────────────────────
# Invigilation Service
# ─────────────────────────────────────────────────────────────────────────────

class ExamInvigilationService:

    @staticmethod
    async def assign(
        session_id: UUID, body: InvigilationCreateIn,
        *, actor_user_id: UUID, actor_role: str,
        tenant_id: UUID, schema_name: str, db: AsyncSession,
    ) -> InvigilationOut:
        session = await ExamSessionRepository.get(db, session_id)
        if session is None:
            raise _not_found("SESSION")
        if session.status in (ExamSessionStatus.COMPLETED,):
            raise ExamServiceError(
                "INVALID_SESSION_STATUS",
                "Cannot assign invigilation to a COMPLETED session.",
            )
        data = body.model_dump()
        data["session_id"]  = session_id
        data["assigned_by"] = actor_user_id
        inv = await ExamInvigilationRepository.create(db, data)
        await AuditService.log(
            db,
            event_type=AuditEventType.EXAM_INVIGILATION_ASSIGNED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SisExamInvigilation",
            target_id=str(inv.id),
            metadata_={"session_id": str(session_id), "faculty": str(body.faculty_user_id)},
        )
        rows = await ExamInvigilationRepository.list_for_session(db, session_id)
        row = next((r for r in rows if str(r["id"]) == str(inv.id)), None)
        if row is None:
            raise ExamServiceError("INVIGILATION_NOT_FOUND", "Invigilation not found.", 500)
        return InvigilationOut.model_validate(row)

    @staticmethod
    async def list_for_session(db: AsyncSession, session_id: UUID) -> list[InvigilationOut]:
        session = await ExamSessionRepository.get(db, session_id)
        if session is None:
            raise _not_found("SESSION")
        rows = await ExamInvigilationRepository.list_for_session(db, session_id)
        return [InvigilationOut.model_validate(r) for r in rows]

    @staticmethod
    async def my_invigilation(
        db: AsyncSession, faculty_user_id: UUID, session_id: Optional[UUID] = None
    ) -> list[InvigilationOut]:
        rows = await ExamInvigilationRepository.list_for_faculty(db, faculty_user_id, session_id)
        return [InvigilationOut.model_validate(r) for r in rows]

    @staticmethod
    async def delete(
        inv_id: UUID,
        *, actor_user_id: UUID, actor_role: str,
        tenant_id: UUID, schema_name: str, db: AsyncSession,
    ) -> None:
        inv = await ExamInvigilationRepository.get(db, inv_id)
        if inv is None:
            raise _not_found("INVIGILATION")
        await ExamInvigilationRepository.delete(db, inv_id)


# ─────────────────────────────────────────────────────────────────────────────
# Seat Allocation Service
# ─────────────────────────────────────────────────────────────────────────────

class ExamSeatingService:

    @staticmethod
    async def allocate_seats(
        session_id: UUID, body: SeatAllocationIn,
        *, actor_user_id: UUID, actor_role: str,
        tenant_id: UUID, schema_name: str, db: AsyncSession,
    ) -> SeatingAllocationResult:
        # Validate session
        session = await ExamSessionRepository.get(db, session_id)
        if session is None:
            raise _not_found("SESSION")
        allowed = (ExamSessionStatus.PUBLISHED, ExamSessionStatus.SEATING_ALLOCATED)
        if session.status not in allowed:
            raise ExamServiceError(
                "INVALID_SESSION_STATUS",
                f"Seat allocation requires session in PUBLISHED or SEATING_ALLOCATED status. "
                f"Current: {session.status}.",
            )

        # Validate center
        center = await ExamCenterRepository.get(db, body.center_id)
        if center is None:
            raise _not_found("CENTER")
        if not center.is_active:
            raise ExamServiceError("CENTER_NOT_ACTIVE", "The selected exam center is inactive.")

        # Get eligible students
        students = await ExamSeatingRepository.get_eligible_students(
            db, session.semester_id, body.section_id
        )
        if not students:
            raise ExamServiceError(
                "NO_ELIGIBLE_STUDENTS",
                "No eligible students with published hall tickets found for seat allocation.",
            )

        # Validate capacity
        total_capacity = sum(r.capacity for r in body.rooms)
        if len(students) > total_capacity:
            deficit = len(students) - total_capacity
            raise ExamServiceError(
                "INSUFFICIENT_CAPACITY",
                f"Total room capacity ({total_capacity}) is less than eligible students "
                f"({len(students)}). Need {deficit} more seats.",
            )

        # Compute seat assignments
        assignments = _compute_seat_assignments(students, body.rooms)

        # Bulk update eligibility rows
        updated = await ExamSeatingRepository.bulk_assign_seats(
            db, session_id, body.center_id, assignments
        )

        # Transition session to SEATING_ALLOCATED + stamp hall ticket tracking
        now = datetime.now(timezone.utc)
        await ExamSessionRepository.update(
            db,
            session_id,
            {
                "status": ExamSessionStatus.SEATING_ALLOCATED,
                "hall_ticket_generated_at": now,
                "hall_ticket_generated_by": actor_user_id,
            },
        )

        # Audit log
        await AuditService.log(
            db,
            event_type=AuditEventType.EXAM_SEATS_ALLOCATED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SisExamSession",
            target_id=str(session_id),
            metadata_={
                "allocated": updated,
                "center_id": str(body.center_id),
                "rooms": len(body.rooms),
            },
        )

        # Build result details
        room_detail_map: dict[str, int] = {}
        for a in assignments:
            room_detail_map[a["room_number"]] = room_detail_map.get(a["room_number"], 0) + 1

        details = [
            RoomAllocationDetail(
                room_number=r.room_number,
                capacity=r.capacity,
                assigned=room_detail_map.get(r.room_number, 0),
            )
            for r in body.rooms
        ]

        return SeatingAllocationResult(
            session_id=session_id,
            allocated=updated,
            rooms_used=sum(1 for d in details if d.assigned > 0),
            total_capacity=total_capacity,
            details=details,
        )

    @staticmethod
    async def list_seating(
        db: AsyncSession,
        session_id: UUID,
        section_id: Optional[UUID] = None,
    ) -> list[StudentSeatOut]:
        session = await ExamSessionRepository.get(db, session_id)
        if session is None:
            raise _not_found("SESSION")
        rows = await ExamSeatingRepository.list_seating(db, session_id, section_id)
        return [StudentSeatOut.model_validate(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Student View Service
# ─────────────────────────────────────────────────────────────────────────────

class ExamStudentService:

    @staticmethod
    async def my_timetable(
        db: AsyncSession, student_id: UUID, session_id: UUID
    ) -> StudentTimetableOut:
        ctx = await ExamStudentRepository.get_student_section_for_session(
            db, student_id, session_id
        )
        if ctx is None:
            raise _not_found("SESSION")
        status = ctx["status"]
        if status == ExamSessionStatus.DRAFT:
            raise ExamServiceError("SESSION_NOT_FOUND", "Session not found.", 404)

        section_id = ctx.get("section_id")
        courses: list[CourseScheduleRow] = []

        if section_id:
            rows = await ExamStudentRepository.get_timetable_for_section(
                db, session_id, section_id
            )
            courses = [
                CourseScheduleRow(
                    course_id=r["course_id"],
                    course_code=r["course_code"],
                    course_title=r["course_title"],
                    exam_date=r["exam_date"],
                    start_time=r["start_time"],
                    end_time=r["end_time"],
                    center_name=r["center_name"],
                    room_number=r["room_number"],
                    is_scheduled=True,
                )
                for r in rows
            ]

        # Get seating info if allocated
        seat: Optional[SeatInfo] = None
        seat_row = await ExamStudentRepository.get_student_seat(
            db, student_id, ctx["semester_id"], session_id
        )
        if seat_row and seat_row.get("room_number") and seat_row.get("seat_number"):
            seat = SeatInfo(
                center_name=seat_row["center_name"] or "Main Campus",
                address=seat_row.get("address"),
                room_number=seat_row["room_number"],
                seat_number=seat_row["seat_number"],
            )

        return StudentTimetableOut(
            session_id=session_id,
            session_name=ctx["session_name"],
            session_type=ctx["session_type"],
            semester_name=ctx["semester_name"],
            seat=seat,
            courses=courses,
        )

    @staticmethod
    async def my_hall_ticket(
        db: AsyncSession, student_id: UUID, session_id: UUID
    ) -> MyHallTicketExamOut:
        ctx = await ExamStudentRepository.get_student_section_for_session(
            db, student_id, session_id
        )
        if ctx is None:
            raise _not_found("SESSION")
        if ctx["status"] == ExamSessionStatus.DRAFT:
            raise ExamServiceError("SESSION_NOT_FOUND", "Session not found.", 404)

        ht_row = await ExamStudentRepository.get_hall_ticket_row(
            db, student_id, ctx["semester_id"]
        )
        if ht_row is None:
            raise ExamServiceError(
                "ELIGIBILITY_NOT_PUBLISHED",
                "Hall ticket not available. Eligibility must be published and hall ticket assigned.",
                403,
            )

        # Seating info
        seat: Optional[SeatInfo] = None
        if ht_row.get("room_number") and ht_row.get("seat_number"):
            seat = SeatInfo(
                center_name=ht_row["center_name"] or "Main Campus",
                address=ht_row.get("address"),
                room_number=ht_row["room_number"],
                seat_number=ht_row["seat_number"],
            )

        # Timetable
        section_id = ctx.get("section_id")
        courses: list[CourseScheduleRow] = []
        if section_id:
            rows = await ExamStudentRepository.get_timetable_for_section(
                db, session_id, section_id
            )
            courses = [
                CourseScheduleRow(
                    course_id=r["course_id"],
                    course_code=r["course_code"],
                    course_title=r["course_title"],
                    exam_date=r["exam_date"],
                    start_time=r["start_time"],
                    end_time=r["end_time"],
                    center_name=r["center_name"],
                    room_number=r["room_number"],
                    is_scheduled=True,
                )
                for r in rows
            ]

        return MyHallTicketExamOut(
            hall_ticket_number=ht_row["hall_ticket_number"],
            student_id=student_id,
            student_name=ht_row.get("student_name"),
            usn=ht_row.get("usn"),
            semester_name=ht_row["semester_name"],
            academic_year=ht_row["academic_year"],
            status=ht_row["status"],
            seat=seat,
            timetable=courses,
            issued_at=ht_row.get("issued_at"),
            exam_session_id=ht_row.get("exam_session_id"),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _orm_to_dict(obj: object) -> dict:
    """Shallow dict of ORM object's __dict__ minus SQLAlchemy internals."""
    return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}


def _compute_seat_assignments(
    students: list[dict], rooms: list[RoomSpec]
) -> list[dict]:
    """
    Assigns seats sequentially: fill rooms in order, then move to next room.
    seat_number format: "{room_number}-{seq:03d}" e.g. "A101-001"
    """
    assignments: list[dict] = []
    room_idx  = 0
    seat_seq  = 0

    for student in students:
        if seat_seq >= rooms[room_idx].capacity:
            room_idx += 1
            seat_seq  = 0
        seat_seq += 1
        room = rooms[room_idx]
        assignments.append({
            "eligibility_id": student["eligibility_id"],
            "room_number":    room.room_number,
            "seat_number":    f"{room.room_number}-{seat_seq:03d}",
        })

    return assignments
