"""
SIS Attendance — H55 Service.

Business rules (all per approved H55 policy decisions):
  - Faculty must hold an active PRIMARY or CO_FACULTY subject_assignment for the
    course in the semester that contains the target section. GUEST role cannot mark.
  - section.semester_id must match the assignment's semester_id (SECTION_MISMATCH).
  - Date rules: a future date is never markable. Past dates are open by default;
    settings.ATTENDANCE_EDIT_WINDOW_DAYS is an optional backward cap (0 = no
    limit, the default) that a deployment can set to restore a rolling window.
    Semester-boundary enforcement is deliberately NOT part of this rule yet.
  - edit_reason is mandatory on any modification after the first save.
  - Phase 1 MVP: only PRESENT/ABSENT are valid statuses.
  - Shortage warning notification fires once per student per (course, section)
    when attendance % first drops below threshold. Default threshold: 75%.
  - Reopen requires mandatory reason; stamps reopened_by, reopened_at, reopen_reason.
  - Advisory principle (Vidya non-negotiable): attendance % is informational.
    No autonomous action is taken based on the threshold.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.models import User
from app.modules.m_academics.class_roster import is_elective_course, resolve_class_roster
from app.modules.m11_sis.attendance_models import (
    SessionStatus, SisAttendanceSession,
)
from app.modules.m11_sis.attendance_repository import (
    DEFAULT_SHORTAGE_THRESHOLD, AttendanceRepository,
)
from app.modules.m11_sis.attendance_schemas import (
    AttendanceDashboardOut, AttendanceMarkIn, AttendanceMarkResult, AttendanceRecordOut,
    CourseAttendanceSummary, FacultyCourseShortage, FacultyDayClassOut, FacultyDayOut,
    FacultyShortageReportOut,
    MyCourseAttendanceDetail, MyAttendanceSummary,
    RecordEditIn, ReopenSessionIn, SectionAttendanceOut, SectionStudentAttendance,
    SessionCreateIn, SessionOut, SessionRecordForStudent,
    SessionUpdateIn, ShortageGroupedOut, ShortageCourseGroup, ShortageSectionGroup,
    ShortageReportOut, ShortageStudentOut,
)
from app.modules.m_academics.dean_scope import get_dean_program_ids
from app.modules.m_academics.models import AcadSection, SubjectAssignment

logger = logging.getLogger("vidya.sis.attendance")

from app.config import settings


async def _resolve_dean_scope(
    caller_role: Optional[str],
    caller_user_id: Optional[UUID],
    *,
    requested_program_id: Optional[UUID],
    db: AsyncSession,
) -> Optional[list[UUID]]:
    """Resolve the acad_programs.id set a caller may see attendance analytics for.

    Returns None for ADMIN/non-DEAN callers (unrestricted). For a DEAN,
    returns their governed program set and raises if they explicitly
    requested a `program_id` outside that scope — a client cannot bypass
    scoping by supplying a program_id it isn't entitled to.
    """
    if caller_role != "DEAN" or caller_user_id is None:
        return None
    governed = await get_dean_program_ids(caller_user_id, caller_role, db)
    if governed is None:
        return None
    if requested_program_id is not None and requested_program_id not in governed:
        raise AttendanceServiceError(
            "PROGRAM_NOT_IN_SCOPE",
            "You may only view attendance analytics for programs you govern.",
            403,
        )
    return governed


# ---------------------------------------------------------------------------
# Helpers: edit window
# ---------------------------------------------------------------------------

def is_within_edit_window(session_date: date) -> bool:
    """May a class on ``session_date`` be taken or edited?

    Two independent rules, and only the first is absolute:

    * **A future date is never markable.** Attendance records what happened, so
      a class that has not been held yet cannot have a register. This holds
      regardless of configuration.
    * **Past dates are open by default.** ``ATTENDANCE_EDIT_WINDOW_DAYS`` is an
      optional backward cap; at its default of 0 there is no backward limit and
      any past teaching date may be marked. A positive value restores a rolling
      window (7 reproduces the historical behaviour exactly).

    The backward cap defaults to off because a hard 7-day limit had no override
    path: attendance that was genuinely late — a timetable published mid-term, a
    register corrected after an audit, a faculty member back from leave — simply
    could not be entered by anyone, at any role.
    """
    today = date.today()
    if session_date > today:
        return False
    max_days = settings.ATTENDANCE_EDIT_WINDOW_DAYS
    if max_days <= 0:
        return True
    return (today - session_date).days <= max_days


def _window_error_message(session_date: date) -> str:
    """Why ``session_date`` was refused, in the words the faculty needs.

    A future date and an over-old date are rejected by the same check but are
    different mistakes: one is never permitted, the other is a configured cap the
    institution can change.
    """
    if session_date > date.today():
        return "Attendance cannot be marked for a future date."
    return (
        f"Attendance can only be taken for today and the previous "
        f"{settings.ATTENDANCE_EDIT_WINDOW_DAYS} days."
    )


def is_editable(session: SisAttendanceSession) -> bool:
    """A session may be taken/edited while OPEN and within the date window."""
    if session.status == SessionStatus.LOCKED:
        return False
    return is_within_edit_window(session.session_date)


def minutes_until_lock(session: SisAttendanceSession) -> Optional[int]:
    """Minutes remaining until the date window closes (midnight after the last
    editable day).

    None when there is nothing to count down to: the session is locked, it is
    already outside the window, or — the default — no backward cap is configured
    at all, in which case the session never expires on its own.
    """
    if session.status == SessionStatus.LOCKED:
        return None
    if not is_within_edit_window(session.session_date):
        return None
    if settings.ATTENDANCE_EDIT_WINDOW_DAYS <= 0:
        return None
    last_day = session.session_date + timedelta(days=settings.ATTENDANCE_EDIT_WINDOW_DAYS)
    close_at = datetime(last_day.year, last_day.month, last_day.day, tzinfo=timezone.utc) + timedelta(days=1)
    remaining = (close_at - datetime.now(timezone.utc)).total_seconds()
    return max(0, int(remaining // 60))


# ---------------------------------------------------------------------------
# Helpers: attendance percentage
# ---------------------------------------------------------------------------

def _compute_pct(attended: int, total_countable: int) -> Optional[float]:
    if total_countable == 0:
        return None
    return round(attended / total_countable * 100, 2)


def _is_at_risk(pct: Optional[float], threshold: float) -> bool:
    return pct is not None and pct < threshold


# ---------------------------------------------------------------------------
# Helper: build ShortageStudentOut from a raw shortage row dict
# ---------------------------------------------------------------------------

def _shortage_student_from_row(r: dict) -> ShortageStudentOut:
    return ShortageStudentOut(
        student_id=UUID(str(r["student_id"])),
        student_name=r["student_name"],
        usn=r.get("usn"),
        email=r["email"],
        # Both null for an elective group, which has no section.
        section_id=UUID(str(r["section_id"])) if r.get("section_id") else None,
        section_name=r.get("section_name"),
        course_id=UUID(str(r["course_id"])),
        course_code=r["course_code"],
        course_title=r["course_title"],
        total_sessions=int(r["total_sessions"]),
        attended_sessions=int(r["attended_sessions"]),
        attendance_pct=float(r["attendance_pct"]) if r["attendance_pct"] is not None else 0.0,
    )


# ---------------------------------------------------------------------------
# Helper: build SessionOut from raw dict row
# ---------------------------------------------------------------------------

def _session_out_from_row(row: dict, session_orm: Optional[SisAttendanceSession] = None) -> SessionOut:
    present  = int(row.get("present_count",  0) or 0)
    absent   = int(row.get("absent_count",   0) or 0)
    total_countable = present + absent
    pct = _compute_pct(present, total_countable)

    # Reconstruct a minimal SisAttendanceSession for is_editable computation
    class _MockSession:
        status = row.get("status", "OPEN")
        first_marked_at = row.get("first_marked_at")
        reopened_at = row.get("reopened_at")

    mock = session_orm if session_orm else _MockSession()
    editable = is_editable(mock)  # type: ignore[arg-type]
    mtl = minutes_until_lock(mock)  # type: ignore[arg-type]

    return SessionOut(
        id=row["id"],
        course_id=row["course_id"],
        course_code=row["course_code"],
        course_title=row["course_title"],
        section_id=row["section_id"],
        section_name=row["section_name"],
        semester_number=row["semester_number"],
        faculty_user_id=row["faculty_user_id"],
        faculty_name=row["faculty_name"],
        session_date=row["session_date"],
        period_number=row.get("period_number"),
        duration_minutes=row.get("duration_minutes"),
        topic_covered=row.get("topic_covered"),
        status=row.get("status", "OPEN"),
        is_editable=editable,
        minutes_until_lock=mtl,
        first_marked_at=row.get("first_marked_at"),
        locked_at=row.get("locked_at"),
        reopened_by=row.get("reopened_by"),
        reopened_at=row.get("reopened_at"),
        reopen_reason=row.get("reopen_reason"),
        total_enrolled=int(row.get("total_enrolled", 0) or 0),
        present_count=present,
        absent_count=absent,
        attendance_pct=pct,
        created_at=row["created_at"],
        updated_at=row.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# Helper: notifications (fire-and-forget)
# ---------------------------------------------------------------------------

async def _notify_safe(
    *,
    notification_type,
    recipient_user_id: UUID,
    recipient_email: Optional[str],
    title: str,
    body: str,
    entity_type: str,
    entity_id: str,
    db: AsyncSession,
) -> None:
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
            "attendance notification_failed type=%s recipient=%s",
            notification_type, recipient_user_id, exc_info=True,
        )


# ---------------------------------------------------------------------------
# Helper: check and fire shortage warnings after marking
# ---------------------------------------------------------------------------

def shortage_entity_id(session: SisAttendanceSession) -> str:
    """Dedup key identifying the class a shortage warning is about.

    A section class keeps the historical `course:section` form so notifications
    already sent stay deduplicated. An elective group has no section, so it is
    keyed by its term instead — otherwise every elective in every semester would
    collapse onto the same `course:None` key.
    """
    if session.section_id is not None:
        return f"{session.course_id}:{session.section_id}"
    return f"{session.course_id}:sem:{session.semester_id}"


async def _check_threshold_and_notify(
    session: SisAttendanceSession,
    affected_student_ids: list[UUID],
    threshold: float,
    db: AsyncSession,
) -> None:
    try:
        entity_id = shortage_entity_id(session)
        pcts = await AttendanceRepository.get_students_course_pct_batch(
            student_ids=affected_student_ids,
            course_id=session.course_id,
            semester_id=session.semester_id,
            section_id=session.section_id,
            db=db,
        )
        for student_id, pct in pcts.items():
            if pct is None or pct >= threshold:
                continue
            already_warned = await AttendanceRepository.check_shortage_warning_exists(
                student_id, entity_id, db
            )
            if already_warned:
                continue
            user = (await db.execute(select(User).where(User.id == student_id))).scalar_one_or_none()
            if user is None:
                continue
            # Fetch course code for the notification body
            course_row = (await db.execute(
                text("SELECT code FROM courses WHERE id = :id"), {"id": str(session.course_id)}
            )).one_or_none()
            course_code = course_row[0] if course_row else str(session.course_id)

            from app.core.notifications.models import NotificationType
            await _notify_safe(
                notification_type=NotificationType.ATTENDANCE_SHORTAGE_WARNING,
                recipient_user_id=user.id,
                recipient_email=user.email,
                title=f"Attendance Warning — {course_code}",
                body=(
                    f"Your attendance in {course_code} has dropped to {pct:.1f}%. "
                    f"Minimum required is {threshold:.0f}%. "
                    "Contact your faculty or Dean for guidance."
                ),
                entity_type="attendance_shortage",
                entity_id=entity_id,
                db=db,
            )
    except Exception:
        logger.warning(
            "attendance threshold_notify_failed session=%s", session.id, exc_info=True,
        )


# ---------------------------------------------------------------------------
# Helper: verify faculty assignment
# ---------------------------------------------------------------------------

async def _assert_faculty_teaches(
    course_id: UUID,
    semester_id: UUID,
    faculty_id: UUID,
    db: AsyncSession,
) -> None:
    """Raise unless `faculty_id` actively teaches `course_id` in this term.

    Assignment is keyed on (course, semester) — never on a section — which is
    what lets one faculty member own an elective taught across several sections.
    """
    assignment = (
        await db.execute(
            select(SubjectAssignment)
            .where(SubjectAssignment.course_id      == course_id)
            .where(SubjectAssignment.semester_id    == semester_id)
            .where(SubjectAssignment.faculty_user_id == faculty_id)
            .where(SubjectAssignment.is_active.is_(True))
            .where(SubjectAssignment.role_in_course.in_(["PRIMARY", "CO_FACULTY"]))
        )
    ).scalar_one_or_none()

    if assignment is None:
        raise AttendanceServiceError(
            "NOT_ASSIGNED",
            "You must be an active PRIMARY or CO_FACULTY for this course in this "
            "semester to mark attendance.",
            403,
        )


async def _verify_faculty_assignment(
    course_id: UUID,
    section_id: UUID,
    faculty_id: UUID,
    db: AsyncSession,
) -> AcadSection:
    """
    Returns the AcadSection if faculty is validly assigned.
    Raises AttendanceServiceError otherwise.
    """
    section = (
        await db.execute(select(AcadSection).where(AcadSection.id == section_id))
    ).scalar_one_or_none()
    if section is None:
        raise AttendanceServiceError("SECTION_NOT_FOUND", "Section not found.", 404)
    if not section.is_active:
        raise AttendanceServiceError("SECTION_INACTIVE", "Section is inactive.", 400)

    await _assert_faculty_teaches(course_id, section.semester_id, faculty_id, db)
    return section


async def _resolve_session_class(
    body: SessionCreateIn,
    faculty_id: UUID,
    db: AsyncSession,
) -> tuple[Optional[UUID], UUID]:
    """Decide which class this session is for, and check the faculty owns it.

    Returns `(section_id, semester_id)`. `section_id is None` marks an elective
    group: everyone in the term who chose this elective, no section split.
    """
    if await is_elective_course(body.course_id, db):
        # An elective is not taught to a section, so accepting one would silently
        # halve the class.
        if body.semester_id is None:
            raise AttendanceServiceError(
                "SEMESTER_REQUIRED",
                "This is an elective. Pass semester_id — its class is every student "
                "who chose it this semester, not a section.",
                422,
            )
        await _assert_faculty_teaches(body.course_id, body.semester_id, faculty_id, db)
        return None, body.semester_id

    if body.section_id is None:
        raise AttendanceServiceError(
            "SECTION_REQUIRED", "This course is taught per section. Pass section_id.", 422,
        )
    section = await _verify_faculty_assignment(body.course_id, body.section_id, faculty_id, db)
    return body.section_id, section.semester_id


# ---------------------------------------------------------------------------
# Service error
# ---------------------------------------------------------------------------

class AttendanceServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# AttendanceService
# ---------------------------------------------------------------------------

class AttendanceService:

    # ------------------------------------------------------------------
    # Faculty: today's classes (redesigned dashboard)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_faculty_today(
        faculty_id: UUID, on_date: date, db: AsyncSession,
    ) -> FacultyDayOut:
        """The signed-in faculty's classes for `on_date`, from their published
        timetable, each annotated with class size and whether attendance was
        already taken that day. Self-scoped — a faculty only ever sees their own
        `faculty_user_id`'s slots."""
        rows = await AttendanceRepository.get_faculty_day_classes(
            faculty_id, on_date.weekday(), on_date, db,
        )
        classes = [
            FacultyDayClassOut(
                course_id=r["course_id"],
                course_code=r["course_code"],
                course_title=r["course_title"],
                is_elective=bool(r["is_elective"]),
                section_id=r["section_id"],
                section_name=r["section_name"],
                semester_id=r["semester_id"],
                semester_label=r["semester_label"],
                period_number=r["period_number"],
                start_time=r["start_time"],
                end_time=r["end_time"],
                period_label=r["period_label"],
                student_count=int(r["student_count"] or 0),
                session_id=r["session_id"],
                # A session created-but-not-yet-saved (first_marked_at NULL) is
                # not "taken" — it holds only the seeded ABSENT rows. Keying on
                # first_marked_at keeps the dashboard honest.
                is_taken=r["first_marked_at"] is not None,
                present_count=int(r["present_count"]) if r["first_marked_at"] is not None else None,
                total_marked=int(r["total_marked"]) if r["first_marked_at"] is not None else None,
            )
            for r in rows
        ]
        return FacultyDayOut(
            on_date=on_date,
            weekday=on_date.weekday(),
            today=classes,
            editable=is_within_edit_window(on_date),
        )

    # ------------------------------------------------------------------
    # Faculty: create session
    # ------------------------------------------------------------------

    @staticmethod
    async def create_session(
        body: SessionCreateIn,
        actor_id: UUID,
        actor_role: str,
        tenant_id: Optional[UUID],
        schema_name: Optional[str],
        db: AsyncSession,
    ) -> SessionOut:
        if not is_within_edit_window(body.session_date):
            raise AttendanceServiceError(
                "EDIT_WINDOW_EXPIRED", _window_error_message(body.session_date), 403,
            )
        section_id, semester_id = await _resolve_session_class(body, actor_id, db)

        session = SisAttendanceSession(
            id=uuid.uuid4(),
            course_id=body.course_id,
            section_id=section_id,
            semester_id=semester_id,
            faculty_user_id=actor_id,
            session_date=body.session_date,
            period_number=body.period_number,
            duration_minutes=body.duration_minutes,
            topic_covered=body.topic_covered,
            status=SessionStatus.OPEN,
        )
        session = await AttendanceRepository.create_session(session, db)

        # Pre-populate the roster as ABSENT. An elective's roster is everyone who
        # chose it this semester, across every section; a regular course's is the
        # section's enrolment. One resolver so attendance and marks never diverge.
        student_ids = await resolve_class_roster(body.course_id, semester_id, section_id, db)
        await AttendanceRepository.bulk_create_absent_records(session.id, student_ids, db)
        await db.commit()

        await AuditService.log(
            AuditEventType.ATTENDANCE_SESSION_CREATED,
            actor_user_id=actor_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SisAttendanceSession",
            target_id=str(session.id),
            metadata={
                "course_id": str(body.course_id),
                "section_id": str(section_id) if section_id else None,
                "semester_id": str(semester_id),
                "is_elective_group": section_id is None,
                "session_date": str(body.session_date),
                "students_enrolled": len(student_ids),
            },
        )

        rows = await AttendanceRepository.list_sessions_enriched(
            faculty_user_id=actor_id,
            course_id=body.course_id,
            # Filter on the class we actually created, not on what the caller
            # sent: an elective session resolves to section_id=None regardless.
            section_id=section_id,
            db=db,
        )
        row = next((r for r in rows if r["id"] == session.id), None)
        if row is None:
            raise AttendanceServiceError("INTERNAL", "Session created but could not be retrieved.", 500)
        return _session_out_from_row(row, session)

    # ------------------------------------------------------------------
    # Faculty: update session metadata
    # ------------------------------------------------------------------

    @staticmethod
    async def update_session(
        session_id: UUID,
        body: SessionUpdateIn,
        actor_id: UUID,
        actor_role: str,
        tenant_id: Optional[UUID],
        schema_name: Optional[str],
        db: AsyncSession,
    ) -> SessionOut:
        session = await AttendanceRepository.get_session_by_id(session_id, db)
        if session is None:
            raise AttendanceServiceError("SESSION_NOT_FOUND", "Session not found.", 404)
        if actor_role == "FACULTY" and session.faculty_user_id != actor_id:
            raise AttendanceServiceError("FORBIDDEN", "You do not own this session.", 403)
        if not is_editable(session):
            raise AttendanceServiceError("WINDOW_CLOSED", "Attendance edit window is closed.", 403)

        if body.topic_covered is not None:
            session.topic_covered = body.topic_covered
        if body.period_number is not None:
            session.period_number = body.period_number
        if body.duration_minutes is not None:
            session.duration_minutes = body.duration_minutes
        session.updated_at = datetime.now(timezone.utc)
        session = await AttendanceRepository.update_session(session, db)
        await db.commit()

        await AuditService.log(
            AuditEventType.ATTENDANCE_SESSION_UPDATED,
            actor_user_id=actor_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SisAttendanceSession",
            target_id=str(session_id),
        )

        rows = await AttendanceRepository.list_sessions_enriched(
            course_id=session.course_id, section_id=session.section_id, db=db
        )
        row = next((r for r in rows if r["id"] == session.id), None)
        if row is None:
            raise AttendanceServiceError("INTERNAL", "Session not found after update.", 500)
        return _session_out_from_row(row, session)

    # ------------------------------------------------------------------
    # Faculty: mark attendance (bulk)
    # ------------------------------------------------------------------

    @staticmethod
    async def mark_attendance(
        session_id: UUID,
        body: AttendanceMarkIn,
        actor_id: UUID,
        actor_role: str,
        tenant_id: Optional[UUID],
        schema_name: Optional[str],
        db: AsyncSession,
        threshold: float = DEFAULT_SHORTAGE_THRESHOLD,
    ) -> AttendanceMarkResult:
        session = await AttendanceRepository.get_session_by_id(session_id, db)
        if session is None:
            raise AttendanceServiceError("SESSION_NOT_FOUND", "Session not found.", 404)

        if actor_role == "FACULTY" and session.faculty_user_id != actor_id:
            raise AttendanceServiceError("FORBIDDEN", "You do not own this session.", 403)
        if not is_editable(session):
            raise AttendanceServiceError("WINDOW_CLOSED", "Attendance edit window is closed.", 403)

        is_first_mark = session.first_marked_at is None
        if not is_first_mark and not body.edit_reason:
            raise AttendanceServiceError(
                "EDIT_REASON_REQUIRED",
                "edit_reason is required when modifying attendance that has already been saved.",
                400,
            )

        records_map = await AttendanceRepository.load_records_map(session_id, db)
        saved, first_marks, edits = await AttendanceRepository.bulk_mark_records(
            records_map=records_map,
            entries=body.records,
            actor_id=actor_id,
            edit_reason=body.edit_reason,
            db=db,
        )

        if is_first_mark and first_marks > 0:
            session.first_marked_at = datetime.now(timezone.utc)
            session.updated_at = session.first_marked_at
            await db.flush()

        await db.commit()

        await AuditService.log(
            AuditEventType.ATTENDANCE_MARKED if is_first_mark else AuditEventType.ATTENDANCE_EDITED,
            actor_user_id=actor_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SisAttendanceSession",
            target_id=str(session_id),
            metadata={
                "session_date": str(session.session_date),
                "saved": saved,
                "first_marks": first_marks,
                "edits": edits,
            },
        )

        # Threshold warning (fire-and-forget)
        affected_ids = [e.student_id for e in body.records]
        await _check_threshold_and_notify(session, affected_ids, threshold, db)

        return AttendanceMarkResult(
            session_id=session_id,
            saved=saved,
            first_marks=first_marks,
            edits=edits,
        )

    # ------------------------------------------------------------------
    # Faculty: edit individual record
    # ------------------------------------------------------------------

    @staticmethod
    async def edit_record(
        session_id: UUID,
        record_id: UUID,
        body: RecordEditIn,
        actor_id: UUID,
        actor_role: str,
        tenant_id: Optional[UUID],
        schema_name: Optional[str],
        db: AsyncSession,
        threshold: float = DEFAULT_SHORTAGE_THRESHOLD,
    ) -> AttendanceRecordOut:
        session = await AttendanceRepository.get_session_by_id(session_id, db)
        if session is None:
            raise AttendanceServiceError("SESSION_NOT_FOUND", "Session not found.", 404)
        if actor_role == "FACULTY" and session.faculty_user_id != actor_id:
            raise AttendanceServiceError("FORBIDDEN", "You do not own this session.", 403)
        if not is_editable(session):
            raise AttendanceServiceError("WINDOW_CLOSED", "Attendance edit window is closed.", 403)

        record = await AttendanceRepository.get_record_by_id(record_id, db)
        if record is None or record.session_id != session_id:
            raise AttendanceServiceError("RECORD_NOT_FOUND", "Attendance record not found.", 404)

        if record.marked_by is not None and not body.edit_reason:
            raise AttendanceServiceError(
                "EDIT_REASON_REQUIRED",
                "edit_reason is required when modifying an already-saved attendance record.",
                400,
            )

        record = await AttendanceRepository.edit_record(
            record, body.status, body.remarks, actor_id, body.edit_reason, db
        )

        if session.first_marked_at is None:
            session.first_marked_at = datetime.now(timezone.utc)
            session.updated_at = session.first_marked_at
            await db.flush()

        await db.commit()

        await AuditService.log(
            AuditEventType.ATTENDANCE_EDITED,
            actor_user_id=actor_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SisAttendanceRecord",
            target_id=str(record_id),
            metadata={
                "session_id": str(session_id),
                "student_id": str(record.student_id),
                "new_status": body.status,
                "edit_reason": body.edit_reason,
            },
        )

        await _check_threshold_and_notify(session, [record.student_id], threshold, db)

        # Return enriched record
        all_records = await AttendanceRepository.get_records_by_session(session_id, db)
        match = next((r for r in all_records if r.id == record_id), None)
        if match is None:
            raise AttendanceServiceError("INTERNAL", "Record not found after update.", 500)
        return match

    # ------------------------------------------------------------------
    # Admin / Dean: reopen locked session
    # ------------------------------------------------------------------

    @staticmethod
    async def reopen_session(
        session_id: UUID,
        body: ReopenSessionIn,
        actor_id: UUID,
        actor_role: str,
        tenant_id: Optional[UUID],
        schema_name: Optional[str],
        db: AsyncSession,
    ) -> SessionOut:
        session = await AttendanceRepository.get_session_by_id(session_id, db)
        if session is None:
            raise AttendanceServiceError("SESSION_NOT_FOUND", "Session not found.", 404)

        if actor_role == "DEAN":
            governed = await get_dean_program_ids(actor_id, actor_role, db)
            if governed is not None:
                from sqlalchemy import select as _select
                from app.modules.m01_program_advisor.models import Course, Program

                acad_program_id = (
                    await db.execute(
                        _select(Program.acad_program_id)
                        .join(Course, Course.program_id == Program.id)
                        .where(Course.id == session.course_id)
                    )
                ).scalar_one_or_none()
                if acad_program_id is None or acad_program_id not in governed:
                    raise AttendanceServiceError(
                        "PROGRAM_NOT_IN_SCOPE",
                        "You may only reopen sessions for programs you govern.",
                        403,
                    )

        now = datetime.now(timezone.utc)
        session.status        = SessionStatus.OPEN
        session.reopened_by   = actor_id
        session.reopened_at   = now
        session.reopen_reason = body.reason
        session.updated_at    = now
        session = await AttendanceRepository.update_session(session, db)
        await db.commit()

        await AuditService.log(
            AuditEventType.ATTENDANCE_SESSION_REOPENED,
            actor_user_id=actor_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="SisAttendanceSession",
            target_id=str(session_id),
            metadata={
                "reopened_by": str(actor_id),
                "reopen_reason": body.reason,
                "session_date": str(session.session_date),
            },
        )

        rows = await AttendanceRepository.list_sessions_enriched(
            course_id=session.course_id, section_id=session.section_id, db=db
        )
        row = next((r for r in rows if r["id"] == session.id), None)
        if row is None:
            raise AttendanceServiceError("INTERNAL", "Session not found after reopen.", 500)
        return _session_out_from_row(row, session)

    # ------------------------------------------------------------------
    # Read: list sessions
    # ------------------------------------------------------------------

    @staticmethod
    async def list_sessions(
        actor_id: UUID,
        actor_role: str,
        course_id:  Optional[UUID] = None,
        section_id: Optional[UUID] = None,
        date_from:  Optional[str]  = None,
        date_to:    Optional[str]  = None,
        status:     Optional[str]  = None,
        db:         AsyncSession = None,  # type: ignore[assignment]
    ) -> list[SessionOut]:
        faculty_filter = actor_id if actor_role == "FACULTY" else None
        rows = await AttendanceRepository.list_sessions_enriched(
            faculty_user_id=faculty_filter,
            course_id=course_id,
            section_id=section_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
            db=db,
        )
        return [_session_out_from_row(r) for r in rows]

    @staticmethod
    async def get_session(
        session_id: UUID,
        actor_id: UUID,
        actor_role: str,
        db: AsyncSession,
    ) -> SessionOut:
        session = await AttendanceRepository.get_session_by_id(session_id, db)
        if session is None:
            raise AttendanceServiceError("SESSION_NOT_FOUND", "Session not found.", 404)
        if actor_role == "FACULTY" and session.faculty_user_id != actor_id:
            raise AttendanceServiceError("FORBIDDEN", "You do not have access to this session.", 403)
        rows = await AttendanceRepository.list_sessions_enriched(
            course_id=session.course_id, section_id=session.section_id, db=db
        )
        row = next((r for r in rows if r["id"] == session.id), None)
        if row is None:
            raise AttendanceServiceError("SESSION_NOT_FOUND", "Session not found.", 404)
        return _session_out_from_row(row, session)

    @staticmethod
    async def get_session_records(
        session_id: UUID,
        actor_id: UUID,
        actor_role: str,
        db: AsyncSession,
    ) -> list[AttendanceRecordOut]:
        session = await AttendanceRepository.get_session_by_id(session_id, db)
        if session is None:
            raise AttendanceServiceError("SESSION_NOT_FOUND", "Session not found.", 404)
        if actor_role == "FACULTY" and session.faculty_user_id != actor_id:
            raise AttendanceServiceError("FORBIDDEN", "You do not have access to this session.", 403)
        return await AttendanceRepository.get_records_by_session(session_id, db)

    # ------------------------------------------------------------------
    # Read: student self-view
    # ------------------------------------------------------------------

    @staticmethod
    async def get_my_attendance(
        student_id: UUID,
        threshold: float,
        db: AsyncSession,
    ) -> MyAttendanceSummary:
        user, profile, rows = await AttendanceRepository.get_student_summary_raw(
            student_id, threshold, db
        )
        if user is None:
            raise AttendanceServiceError("STUDENT_NOT_FOUND", "Student not found.", 404)

        courses: list[CourseAttendanceSummary] = []
        for row in rows:
            total    = int(row["total_sessions"])
            attended = int(row["attended_count"])
            pct = _compute_pct(attended, total)
            courses.append(CourseAttendanceSummary(
                course_id=UUID(str(row["course_id"])),
                course_code=row["course_code"],
                course_title=row["course_title"],
                total_sessions=total,
                attended_sessions=attended,
                attendance_pct=pct,
                is_at_risk=_is_at_risk(pct, threshold),
            ))

        # Overall % = (sum attended) / (sum total) across all courses
        total_attended = sum(c.attended_sessions for c in courses)
        total_sessions = sum(c.total_sessions    for c in courses)
        overall_pct = _compute_pct(total_attended, total_sessions)

        return MyAttendanceSummary(
            student_id=student_id,
            student_name=user.full_name,
            usn=profile.usn if profile else None,
            overall_pct=overall_pct,
            courses=courses,
        )

    @staticmethod
    async def get_my_course_detail(
        student_id: UUID,
        course_id: UUID,
        threshold: float,
        db: AsyncSession,
    ) -> MyCourseAttendanceDetail:
        _, profile, summary_rows = await AttendanceRepository.get_student_summary_raw(
            student_id, threshold, db
        )
        course_row = next(
            (r for r in summary_rows if str(r["course_id"]) == str(course_id)), None
        )
        if course_row is None:
            raise AttendanceServiceError("COURSE_NOT_FOUND", "No attendance found for this course.", 404)

        total    = int(course_row["total_sessions"])
        attended = int(course_row["attended_count"])
        pct = _compute_pct(attended, total)

        summary = CourseAttendanceSummary(
            course_id=UUID(str(course_row["course_id"])),
            course_code=course_row["course_code"],
            course_title=course_row["course_title"],
            total_sessions=total,
            attended_sessions=attended,
            attendance_pct=pct,
            is_at_risk=_is_at_risk(pct, threshold),
        )

        session_rows = await AttendanceRepository.get_student_course_sessions(
            student_id, course_id, db
        )
        sessions = [
            SessionRecordForStudent(
                session_id=UUID(str(r["session_id"])),
                session_date=r["session_date"],
                period_number=r.get("period_number"),
                topic_covered=r.get("topic_covered"),
                status=r["status"],
                remarks=r.get("remarks"),
                course_code=r.get("course_code"),
                course_title=r.get("course_title"),
                faculty_name=r.get("faculty_name"),
                start_time=r.get("start_time"),
                end_time=r.get("end_time"),
                session_type=r.get("session_type") or "THEORY",
            )
            for r in session_rows
        ]

        return MyCourseAttendanceDetail(
            course_id=summary.course_id,
            course_code=summary.course_code,
            course_title=summary.course_title,
            summary=summary,
            sessions=sessions,
        )

    # ------------------------------------------------------------------
    # Analytics: section
    # ------------------------------------------------------------------

    @staticmethod
    async def get_section_analytics(
        section_id: UUID,
        threshold: float,
        db: AsyncSession,
        *,
        caller_role: str = "",
        caller_user_id: UUID | None = None,
    ) -> SectionAttendanceOut:
        # A faculty may only see a section's attendance figures if they teach in
        # that section's term — otherwise every section's full attendance is one
        # guessable id away. ADMIN/DEAN are unrestricted here (Dean scope is
        # enforced by the shortage-report endpoints, not this per-section read).
        if caller_role == "FACULTY" and caller_user_id is not None:
            from app.modules.m_academics.faculty_scope import faculty_teaches_in_section
            if not await faculty_teaches_in_section(caller_user_id, section_id, db):
                raise AttendanceServiceError(
                    "FORBIDDEN", "You do not teach in this section.", 403,
                )

        context, rows = await AttendanceRepository.get_section_analytics_raw(
            section_id, threshold, db
        )
        if not context:
            raise AttendanceServiceError("SECTION_NOT_FOUND", "Section not found.", 404)

        students: list[SectionStudentAttendance] = []
        for row in rows:
            total    = int(row["total_sessions"])
            attended = int(row["attended_count"])
            pct = _compute_pct(attended, total)
            students.append(SectionStudentAttendance(
                student_id=UUID(str(row["student_id"])),
                student_name=row["full_name"],
                usn=row.get("usn"),
                total_sessions=total,
                attended_sessions=attended,
                attendance_pct=pct,
                is_at_risk=_is_at_risk(pct, threshold),
            ))

        valid_pcts = [s.attendance_pct for s in students if s.attendance_pct is not None]
        avg_pct = round(sum(valid_pcts) / len(valid_pcts), 2) if valid_pcts else None
        total_sessions = max((s.total_sessions for s in students), default=0)

        return SectionAttendanceOut(
            section_id=UUID(str(context["section_id"])),
            section_name=str(context["section_name"]),
            semester_number=int(context["semester_number"]),
            batch_name=str(context["batch_name"]),
            program_name=str(context["program_name"]),
            total_sessions=total_sessions,
            avg_attendance_pct=avg_pct,
            students=students,
        )

    # ------------------------------------------------------------------
    # Analytics: shortage report (flat list)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_shortage_report(
        threshold: float,
        semester_id:    Optional[UUID],
        section_id:     Optional[UUID],
        course_id:      Optional[UUID],
        db: AsyncSession,
        *,
        program_id:     Optional[UUID] = None,
        batch_id:       Optional[UUID] = None,
        finalized_only: bool = False,
        caller_role:    Optional[str] = None,
        caller_user_id: Optional[UUID] = None,
    ) -> ShortageReportOut:
        allowed_program_ids = await _resolve_dean_scope(
            caller_role, caller_user_id, requested_program_id=program_id, db=db
        )
        rows = await AttendanceRepository.get_shortage_raw(
            threshold, semester_id, section_id, course_id, db,
            program_id=program_id, batch_id=batch_id, finalized_only=finalized_only,
            allowed_program_ids=allowed_program_ids,
        )
        students = [_shortage_student_from_row(r) for r in rows]
        return ShortageReportOut(
            threshold_pct=threshold,
            finalized_only=finalized_only,
            total_at_risk=len(students),
            students=students,
        )

    # ------------------------------------------------------------------
    # Analytics: grouped shortage report — Dean / Admin (H56)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_shortage_grouped(
        threshold: float,
        semester_id:    Optional[UUID],
        db: AsyncSession,
        *,
        program_id:     Optional[UUID] = None,
        batch_id:       Optional[UUID] = None,
        finalized_only: bool = False,
        caller_role:    Optional[str] = None,
        caller_user_id: Optional[UUID] = None,
    ) -> ShortageGroupedOut:
        allowed_program_ids = await _resolve_dean_scope(
            caller_role, caller_user_id, requested_program_id=program_id, db=db
        )
        rows = await AttendanceRepository.get_shortage_raw(
            threshold, semester_id, None, None, db,
            program_id=program_id, batch_id=batch_id, finalized_only=finalized_only,
            allowed_program_ids=allowed_program_ids,
        )

        # Group: course_id → section_id → students
        course_map: dict[str, dict] = {}
        for row in rows:
            cid = str(row["course_id"])
            sid = str(row["section_id"])

            if cid not in course_map:
                course_map[cid] = {
                    "course_id":   UUID(cid),
                    "course_code": row["course_code"],
                    "course_title": row["course_title"],
                    "sections":    {},
                }
            if sid not in course_map[cid]["sections"]:
                course_map[cid]["sections"][sid] = {
                    "section_id":      UUID(sid),
                    "section_name":    row["section_name"],
                    "semester_number": int(row.get("semester_number") or 0),
                    "students":        [],
                }
            course_map[cid]["sections"][sid]["students"].append(
                _shortage_student_from_row(row)
            )

        all_student_ids: set[str] = set()
        course_groups: list[ShortageCourseGroup] = []
        for cd in course_map.values():
            section_groups: list[ShortageSectionGroup] = []
            for sd in cd["sections"].values():
                sts = sd["students"]
                pcts = [s.attendance_pct for s in sts if s.attendance_pct is not None]
                avg_pct = round(sum(pcts) / len(pcts), 2) if pcts else None
                for s in sts:
                    all_student_ids.add(str(s.student_id))
                section_groups.append(ShortageSectionGroup(
                    section_id=sd["section_id"],
                    section_name=sd["section_name"],
                    semester_number=sd["semester_number"],
                    at_risk_count=len(sts),
                    avg_pct=avg_pct,
                    students=sts,
                ))
            course_groups.append(ShortageCourseGroup(
                course_id=cd["course_id"],
                course_code=cd["course_code"],
                course_title=cd["course_title"],
                total_at_risk=sum(sg.at_risk_count for sg in section_groups),
                sections=section_groups,
            ))

        course_groups.sort(key=lambda c: c.total_at_risk, reverse=True)

        return ShortageGroupedOut(
            threshold_pct=threshold,
            finalized_only=finalized_only,
            total_courses_with_shortage=len(course_groups),
            total_students_at_risk=len(all_student_ids),
            courses=course_groups,
        )

    # ------------------------------------------------------------------
    # Analytics: faculty-scoped shortage report (H56)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_faculty_shortage_report(
        faculty_id: UUID,
        threshold: float,
        db: AsyncSession,
        *,
        course_id:      Optional[UUID] = None,
        section_id:     Optional[UUID] = None,
        finalized_only: bool = False,
    ) -> FacultyShortageReportOut:
        rows = await AttendanceRepository.get_faculty_shortage_raw(
            faculty_id, threshold, db,
            course_id=course_id, section_id=section_id, finalized_only=finalized_only,
        )

        # Group by (course_id, section_id) — each combination is one card
        group_map: dict[tuple, dict] = {}
        for row in rows:
            key = (str(row["course_id"]), str(row["section_id"]))
            if key not in group_map:
                group_map[key] = {
                    "course_id":      UUID(str(row["course_id"])),
                    "course_code":    row["course_code"],
                    "course_title":   row["course_title"],
                    "section_id":     UUID(str(row["section_id"])),
                    "section_name":   row["section_name"],
                    "semester_number": int(row.get("semester_number") or 0),
                    "total_enrolled": int(row.get("total_enrolled") or 0),
                    "students":       [],
                }
            group_map[key]["students"].append(_shortage_student_from_row(row))

        courses: list[FacultyCourseShortage] = [
            FacultyCourseShortage(
                course_id=gd["course_id"],
                course_code=gd["course_code"],
                course_title=gd["course_title"],
                section_id=gd["section_id"],
                section_name=gd["section_name"],
                semester_number=gd["semester_number"],
                at_risk_count=len(gd["students"]),
                total_enrolled=gd["total_enrolled"],
                students=gd["students"],
            )
            for gd in group_map.values()
        ]
        courses.sort(key=lambda c: (c.course_code, c.section_name))

        return FacultyShortageReportOut(
            faculty_id=faculty_id,
            threshold_pct=threshold,
            finalized_only=finalized_only,
            total_at_risk=sum(c.at_risk_count for c in courses),
            courses=courses,
        )

    # ------------------------------------------------------------------
    # Analytics: dashboard
    # ------------------------------------------------------------------

    @staticmethod
    async def get_dashboard(
        threshold: float,
        semester_id: Optional[UUID],
        db: AsyncSession,
        *,
        caller_role:    Optional[str] = None,
        caller_user_id: Optional[UUID] = None,
    ) -> AttendanceDashboardOut:
        allowed_program_ids = await _resolve_dean_scope(
            caller_role, caller_user_id, requested_program_id=None, db=db
        )
        data = await AttendanceRepository.get_dashboard_raw(
            threshold, semester_id, db, allowed_program_ids=allowed_program_ids
        )
        return AttendanceDashboardOut(**data)
