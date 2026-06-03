"""
SIS Attendance — H55 Service.

Business rules (all per approved H55 policy decisions):
  - Faculty must hold an active PRIMARY or CO_FACULTY subject_assignment for the
    course in the semester that contains the target section. GUEST role cannot mark.
  - section.semester_id must match the assignment's semester_id (SECTION_MISMATCH).
  - Edit window: 48 hours from first_marked_at (not session created_at).
    If first_marked_at is None, session is editable (window not yet started).
    After reopen: 48 hours from reopened_at.
  - edit_reason is mandatory on any modification after the first save.
  - LATE counts as attended in numerator.
  - EXCUSED is excluded from both numerator and denominator.
  - Shortage warning notification fires once per student per (course, section)
    when attendance % first drops below threshold. Default threshold: 75%.
  - Reopen requires mandatory reason; stamps reopened_by, reopened_at, reopen_reason.
  - Advisory principle (Vidya non-negotiable): attendance % is informational.
    No autonomous action is taken based on the threshold.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.models import User
from app.modules.m11_sis.attendance_models import (
    AttendanceStatus, SessionStatus, SisAttendanceRecord, SisAttendanceSession,
)
from app.modules.m11_sis.attendance_repository import (
    DEFAULT_SHORTAGE_THRESHOLD, AttendanceRepository,
)
from app.modules.m11_sis.attendance_schemas import (
    AttendanceDashboardOut, AttendanceMarkIn, AttendanceMarkResult, AttendanceRecordOut,
    CourseAttendanceSummary, MyCourseAttendanceDetail, MyAttendanceSummary,
    RecordEditIn, ReopenSessionIn, SectionAttendanceOut, SectionStudentAttendance,
    SessionCreateIn, SessionOut, SessionRecordForStudent,
    SessionUpdateIn, ShortageReportOut, ShortageStudentOut,
)
from app.modules.m_academics.models import AcadSection, SubjectAssignment

logger = logging.getLogger("vidya.sis.attendance")

ATTENDANCE_EDIT_WINDOW_HOURS: int = 48


# ---------------------------------------------------------------------------
# Helpers: edit window
# ---------------------------------------------------------------------------

def is_editable(session: SisAttendanceSession) -> bool:
    """
    Session is editable if:
      1. status is OPEN, AND
      2. first_marked_at is None (window not started), OR
         now() is within 48h of (reopened_at or first_marked_at)
    """
    if session.status == SessionStatus.LOCKED:
        return False
    if session.first_marked_at is None:
        return True  # never marked; window not started
    reference = session.reopened_at or session.first_marked_at
    return datetime.now(timezone.utc) < reference + timedelta(hours=ATTENDANCE_EDIT_WINDOW_HOURS)


def minutes_until_lock(session: SisAttendanceSession) -> Optional[int]:
    """Minutes remaining in edit window. None if not started or already locked."""
    if session.status == SessionStatus.LOCKED or session.first_marked_at is None:
        return None
    reference = session.reopened_at or session.first_marked_at
    deadline  = reference + timedelta(hours=ATTENDANCE_EDIT_WINDOW_HOURS)
    remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
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
# Helper: build SessionOut from raw dict row
# ---------------------------------------------------------------------------

def _session_out_from_row(row: dict, session_orm: Optional[SisAttendanceSession] = None) -> SessionOut:
    present  = int(row.get("present_count",  0) or 0)
    absent   = int(row.get("absent_count",   0) or 0)
    late     = int(row.get("late_count",     0) or 0)
    excused  = int(row.get("excused_count",  0) or 0)
    total_countable = present + absent + late
    pct = _compute_pct(present + late, total_countable)

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
        late_count=late,
        excused_count=excused,
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

async def _check_threshold_and_notify(
    session: SisAttendanceSession,
    affected_student_ids: list[UUID],
    threshold: float,
    db: AsyncSession,
) -> None:
    try:
        pcts = await AttendanceRepository.get_students_course_pct_batch(
            student_ids=affected_student_ids,
            course_id=session.course_id,
            section_id=session.section_id,
            db=db,
        )
        for student_id, pct in pcts.items():
            if pct is None or pct >= threshold:
                continue
            already_warned = await AttendanceRepository.check_shortage_warning_exists(
                student_id, session.course_id, session.section_id, db
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
                entity_id=f"{session.course_id}:{session.section_id}",
                db=db,
            )
    except Exception:
        logger.warning(
            "attendance threshold_notify_failed session=%s", session.id, exc_info=True,
        )


# ---------------------------------------------------------------------------
# Helper: verify faculty assignment
# ---------------------------------------------------------------------------

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

    assignment = (
        await db.execute(
            select(SubjectAssignment)
            .where(SubjectAssignment.course_id      == course_id)
            .where(SubjectAssignment.semester_id    == section.semester_id)
            .where(SubjectAssignment.faculty_user_id == faculty_id)
            .where(SubjectAssignment.is_active.is_(True))
            .where(SubjectAssignment.role_in_course.in_(["PRIMARY", "CO_FACULTY"]))
        )
    ).scalar_one_or_none()

    if assignment is None:
        raise AttendanceServiceError(
            "NOT_ASSIGNED",
            "You must be an active PRIMARY or CO_FACULTY for this course in the "
            "section's semester to mark attendance.",
            403,
        )
    return section


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
        await _verify_faculty_assignment(body.course_id, body.section_id, actor_id, db)

        session = SisAttendanceSession(
            id=uuid.uuid4(),
            course_id=body.course_id,
            section_id=body.section_id,
            faculty_user_id=actor_id,
            session_date=body.session_date,
            period_number=body.period_number,
            duration_minutes=body.duration_minutes,
            topic_covered=body.topic_covered,
            status=SessionStatus.OPEN,
        )
        session = await AttendanceRepository.create_session(session, db)

        # Pre-populate all enrolled students as ABSENT
        student_ids = await AttendanceRepository.get_enrolled_student_ids(body.section_id, db)
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
                "section_id": str(body.section_id),
                "session_date": str(body.session_date),
                "students_enrolled": len(student_ids),
            },
        )

        rows = await AttendanceRepository.list_sessions_enriched(
            faculty_user_id=actor_id,
            course_id=body.course_id,
            section_id=body.section_id,
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
            total   = int(row["total_sessions"])
            excused = int(row["excused_count"])
            attended = int(row["attended_count"])
            countable = total - excused
            pct = _compute_pct(attended, countable)
            courses.append(CourseAttendanceSummary(
                course_id=UUID(str(row["course_id"])),
                course_code=row["course_code"],
                course_title=row["course_title"],
                total_sessions=total,
                attended_sessions=attended,
                excused_sessions=excused,
                total_countable=countable,
                attendance_pct=pct,
                is_at_risk=_is_at_risk(pct, threshold),
            ))

        # Overall % = (sum attended) / (sum countable) across all courses
        total_attended  = sum(c.attended_sessions for c in courses)
        total_countable = sum(c.total_countable   for c in courses)
        overall_pct = _compute_pct(total_attended, total_countable)

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

        total   = int(course_row["total_sessions"])
        excused = int(course_row["excused_count"])
        attended = int(course_row["attended_count"])
        countable = total - excused
        pct = _compute_pct(attended, countable)

        summary = CourseAttendanceSummary(
            course_id=UUID(str(course_row["course_id"])),
            course_code=course_row["course_code"],
            course_title=course_row["course_title"],
            total_sessions=total,
            attended_sessions=attended,
            excused_sessions=excused,
            total_countable=countable,
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
    ) -> SectionAttendanceOut:
        context, rows = await AttendanceRepository.get_section_analytics_raw(
            section_id, threshold, db
        )
        if not context:
            raise AttendanceServiceError("SECTION_NOT_FOUND", "Section not found.", 404)

        students: list[SectionStudentAttendance] = []
        for row in rows:
            total   = int(row["total_sessions"])
            excused = int(row["excused_count"])
            attended = int(row["attended_count"])
            countable = total - excused
            pct = _compute_pct(attended, countable)
            students.append(SectionStudentAttendance(
                student_id=UUID(str(row["student_id"])),
                student_name=row["full_name"],
                usn=row.get("usn"),
                total_sessions=total,
                attended_sessions=attended,
                total_countable=countable,
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
    # Analytics: shortage report
    # ------------------------------------------------------------------

    @staticmethod
    async def get_shortage_report(
        threshold: float,
        semester_id: Optional[UUID],
        section_id:  Optional[UUID],
        course_id:   Optional[UUID],
        db: AsyncSession,
    ) -> ShortageReportOut:
        rows = await AttendanceRepository.get_shortage_raw(
            threshold, semester_id, section_id, course_id, db
        )
        students = [
            ShortageStudentOut(
                student_id=UUID(str(r["student_id"])),
                student_name=r["student_name"],
                usn=r.get("usn"),
                email=r["email"],
                section_id=UUID(str(r["section_id"])),
                section_name=r["section_name"],
                course_id=UUID(str(r["course_id"])),
                course_code=r["course_code"],
                course_title=r["course_title"],
                total_sessions=int(r["total_sessions"]),
                attended_sessions=int(r["attended_sessions"]),
                total_countable=int(r["total_countable"]),
                attendance_pct=float(r["attendance_pct"]) if r["attendance_pct"] is not None else 0.0,
            )
            for r in rows
        ]
        return ShortageReportOut(
            threshold_pct=threshold,
            total_at_risk=len(students),
            students=students,
        )

    # ------------------------------------------------------------------
    # Analytics: dashboard
    # ------------------------------------------------------------------

    @staticmethod
    async def get_dashboard(
        threshold: float,
        semester_id: Optional[UUID],
        db: AsyncSession,
    ) -> AttendanceDashboardOut:
        data = await AttendanceRepository.get_dashboard_raw(threshold, semester_id, db)
        return AttendanceDashboardOut(**data)
