"""
SIS Hall Ticket Eligibility — H58 Service.

Business rules:
  - Only ADMIN and DEAN can compute, publish, override, and generate batches.
  - FACULTY can view advisory (own sections only).
  - STUDENT can view only their own PUBLISHED eligibility.
  - Compute → rows created/updated as DRAFT; existing PUBLISHED+overridden rows untouched.
  - Override requires reason ≥ 20 chars; target status must be ELIGIBLE or CONDITIONAL.
  - Publish moves DRAFT → PUBLISHED for a semester (or section scope).
  - Batch generation requires at least one PUBLISHED ELIGIBLE/CONDITIONAL row.
  - Hall ticket number format: {ticket_prefix}-{USN}  e.g. TOCS-2026S2-4CS22CS001
    Fallback for no USN: {ticket_prefix}-{seq:04d}
  - All override and batch generation events are audit-logged.
  - AI advises, humans decide: compute result is advisory until published.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.modules.m11_sis.hallticket_models import (
    SisHallTicketBatch, SisHallTicketEligibility,
    EligibilityStatus, PublishStatus, BatchScope,
)
from app.modules.m11_sis.hallticket_repository import HallTicketRepository
from app.modules.m11_sis.hallticket_schemas import (
    AdvisoryStudentRow, EligibilityComputeIn, EligibilityComputeResult,
    EligibilityDashboardOut, EligibilityOut, EligibilityOverrideIn,
    EligibilityPublishIn, EligibilityPublishResult,
    FacultyAdvisoryOut, HallTicketBatchCreateIn, HallTicketBatchOut,
    HallTicketOut, MyEligibilityOut, EligibilityCheckItemOut,
)

logger = logging.getLogger("vidya.sis.hallticket")


# ---------------------------------------------------------------------------
# Service error
# ---------------------------------------------------------------------------

class HallTicketServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_failure_reasons(
    *,
    attendance_pct:   Optional[Decimal],
    has_shortage:     bool,
    marks_all_locked: bool,
    marks_all_filled: bool,
    has_att_data:     bool,
    has_marks_data:   bool,
    threshold_pct:    float,
) -> list[str]:
    reasons: list[str] = []

    if has_att_data:
        if attendance_pct is not None and float(attendance_pct) < threshold_pct:
            reasons.append(
                f"Attendance {attendance_pct}% is below the required {threshold_pct}%"
            )
        if has_shortage:
            reasons.append("Attendance shortage detected in one or more subjects")
    else:
        # advisory note — no sessions yet
        pass

    if has_marks_data:
        if not marks_all_locked:
            reasons.append("Internal marks not yet finalized (one or more components not LOCKED)")
        elif not marks_all_filled:
            reasons.append("Internal marks incomplete (marks not entered for all LOCKED components)")

    return reasons


def _determine_status(
    *,
    failure_reasons: list[str],
) -> str:
    return EligibilityStatus.ELIGIBLE if not failure_reasons else EligibilityStatus.NOT_ELIGIBLE


def _row_to_out(row: dict) -> EligibilityOut:
    return EligibilityOut(
        id              = row["id"],
        student_id      = row["student_id"],
        student_name    = row.get("student_name", ""),
        usn             = row.get("usn"),
        email           = row.get("email", ""),
        semester_id     = row["semester_id"],
        publish_status  = row["publish_status"],
        status          = row["status"],
        computed_at     = row.get("computed_at"),
        attendance_threshold_used = row.get("attendance_threshold_used", Decimal("75.0")),
        computed_academic_year    = row.get("computed_academic_year", ""),
        computed_semester_name    = row.get("computed_semester_name", ""),
        attendance_pct   = row.get("attendance_pct"),
        has_shortage     = bool(row.get("has_shortage", False)),
        marks_all_locked = bool(row.get("marks_all_locked", False)),
        marks_all_filled = bool(row.get("marks_all_filled", False)),
        failure_reasons  = row.get("failure_reasons") or [],
        is_overridden    = row.get("override_by") is not None,
        override_by      = row.get("override_by"),
        override_at      = row.get("override_at"),
        override_reason  = row.get("override_reason"),
        override_status  = row.get("override_status"),
        hall_ticket_number = row.get("hall_ticket_number"),
        batch_id           = row.get("batch_id"),
        exam_session_id    = row.get("exam_session_id"),
        exam_schedule_id   = row.get("exam_schedule_id"),
        exam_center_id     = row.get("exam_center_id"),
        room_number        = row.get("room_number"),
        seat_number        = row.get("seat_number"),
        created_at         = row["created_at"],
        updated_at         = row.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class HallTicketService:

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------

    @staticmethod
    async def compute(
        body:         EligibilityComputeIn,
        *,
        actor_id:     UUID,
        actor_role:   str,
        tenant_id:    UUID,
        schema_name:  str,
        db:           AsyncSession,
    ) -> EligibilityComputeResult:
        meta = await HallTicketRepository.get_semester_meta(body.semester_id, db)
        if not meta:
            raise HallTicketServiceError("SEMESTER_NOT_FOUND", "Semester not found", 404)

        engine_rows = await HallTicketRepository.compute_eligibility_rows(
            semester_id   = body.semester_id,
            section_id    = body.section_id,
            threshold_pct = body.threshold_pct,
            db            = db,
        )

        if not engine_rows:
            raise HallTicketServiceError(
                "NO_ENROLLMENTS",
                "No active enrollments found for the specified scope",
                404,
            )

        academic_year  = f"{meta['start_year']}-{meta['end_year']}"
        semester_name  = meta["label"]
        threshold      = Decimal(str(body.threshold_pct))
        now            = datetime.now(timezone.utc)

        eligible_count     = 0
        not_eligible_count = 0
        skipped            = 0

        for eng in engine_rows:
            att_pct    = eng.get("attendance_pct")
            shortage   = bool(eng.get("has_shortage", False))
            locked     = bool(eng.get("marks_all_locked", True))
            filled     = bool(eng.get("marks_all_filled", True))
            has_att    = bool(eng.get("has_att_data", False))
            has_marks  = bool(eng.get("has_marks_data", False))

            reasons = _build_failure_reasons(
                attendance_pct   = att_pct,
                has_shortage     = shortage,
                marks_all_locked = locked,
                marks_all_filled = filled,
                has_att_data     = has_att,
                has_marks_data   = has_marks,
                threshold_pct    = body.threshold_pct,
            )
            status = _determine_status(failure_reasons=reasons)

            row = SisHallTicketEligibility(
                id                        = uuid.uuid4(),
                student_id                = eng["student_id"],
                semester_id               = body.semester_id,
                publish_status            = PublishStatus.DRAFT,
                status                    = status,
                computed_at               = now,
                attendance_threshold_used = threshold,
                computed_academic_year    = academic_year,
                computed_semester_name    = semester_name,
                attendance_pct            = att_pct,
                has_shortage              = shortage,
                marks_all_locked          = locked,
                marks_all_filled          = filled,
                failure_reasons           = reasons or None,
            )

            await HallTicketRepository.upsert_eligibility(row, db)

            if status == EligibilityStatus.ELIGIBLE:
                eligible_count += 1
            else:
                not_eligible_count += 1

        await AuditService.log(
            event_type    = AuditEventType.DATA_ACCESS,
            actor_user_id = actor_id,
            tenant_id     = tenant_id,
            resource_type = "hall_ticket_eligibility",
            resource_id   = str(body.semester_id),
            action        = "compute_eligibility",
            metadata      = {
                "semester_id":   str(body.semester_id),
                "section_id":    str(body.section_id) if body.section_id else None,
                "threshold_pct": body.threshold_pct,
                "processed":     len(engine_rows),
                "eligible":      eligible_count,
                "not_eligible":  not_eligible_count,
            },
            schema_name   = schema_name,
            db            = db,
        )

        return EligibilityComputeResult(
            semester_id        = body.semester_id,
            section_id         = body.section_id,
            threshold_pct      = body.threshold_pct,
            processed          = len(engine_rows),
            eligible_count     = eligible_count,
            not_eligible_count = not_eligible_count,
            skipped_overridden = skipped,
        )

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    @staticmethod
    async def publish(
        body:        EligibilityPublishIn,
        *,
        actor_id:    UUID,
        tenant_id:   UUID,
        schema_name: str,
        db:          AsyncSession,
    ) -> EligibilityPublishResult:
        published = await HallTicketRepository.publish_semester(
            semester_id = body.semester_id,
            section_id  = body.section_id,
            db          = db,
        )

        existing_rows = await HallTicketRepository.list_by_semester(
            semester_id    = body.semester_id,
            section_id     = body.section_id,
            publish_status = PublishStatus.PUBLISHED,
            db             = db,
        )
        already_published = len(existing_rows) - published

        await AuditService.log(
            event_type    = AuditEventType.DATA_ACCESS,
            actor_user_id = actor_id,
            tenant_id     = tenant_id,
            resource_type = "hall_ticket_eligibility",
            resource_id   = str(body.semester_id),
            action        = "publish_eligibility",
            metadata      = {
                "semester_id": str(body.semester_id),
                "section_id":  str(body.section_id) if body.section_id else None,
                "published":   published,
            },
            schema_name = schema_name,
            db          = db,
        )

        return EligibilityPublishResult(
            semester_id        = body.semester_id,
            published          = published,
            already_published  = max(already_published, 0),
        )

    # ------------------------------------------------------------------
    # Get eligibility dashboard (Dean / Admin)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_dashboard(
        *,
        semester_id:    UUID,
        section_id:     Optional[UUID],
        status:         Optional[str],
        publish_status: Optional[str],
        has_shortage:   Optional[bool],
        db:             AsyncSession,
    ) -> EligibilityDashboardOut:
        meta = await HallTicketRepository.get_semester_meta(semester_id, db)
        if not meta:
            raise HallTicketServiceError("SEMESTER_NOT_FOUND", "Semester not found", 404)

        rows = await HallTicketRepository.list_by_semester(
            semester_id    = semester_id,
            section_id     = section_id,
            status         = status,
            publish_status = publish_status,
            has_shortage   = has_shortage,
            db             = db,
        )

        eligible_count     = sum(1 for r in rows if r["status"] == EligibilityStatus.ELIGIBLE)
        not_eligible_count = sum(1 for r in rows if r["status"] == EligibilityStatus.NOT_ELIGIBLE)
        conditional_count  = sum(1 for r in rows if r["status"] == EligibilityStatus.CONDITIONAL)
        draft_count        = sum(1 for r in rows if r["publish_status"] == PublishStatus.DRAFT)
        published_count    = sum(1 for r in rows if r["publish_status"] == PublishStatus.PUBLISHED)

        return EligibilityDashboardOut(
            semester_id        = semester_id,
            semester_name      = meta["label"],
            total_students     = len(rows),
            eligible_count     = eligible_count,
            not_eligible_count = not_eligible_count,
            conditional_count  = conditional_count,
            draft_count        = draft_count,
            published_count    = published_count,
            rows               = [_row_to_out(r) for r in rows],
        )

    # ------------------------------------------------------------------
    # Get single eligibility row
    # ------------------------------------------------------------------

    @staticmethod
    async def get_eligibility(eligibility_id: UUID, db: AsyncSession) -> EligibilityOut:
        row = await HallTicketRepository.get_by_id(eligibility_id, db)
        if not row:
            raise HallTicketServiceError("NOT_FOUND", "Eligibility record not found", 404)

        enriched = await HallTicketRepository.list_by_semester(
            semester_id = row.semester_id,
            db          = db,
        )
        match = next((r for r in enriched if r["id"] == row.id), None)
        if not match:
            raise HallTicketServiceError("NOT_FOUND", "Eligibility record not found", 404)
        return _row_to_out(match)

    # ------------------------------------------------------------------
    # Override (human gate)
    # ------------------------------------------------------------------

    @staticmethod
    async def override(
        eligibility_id: UUID,
        body:           EligibilityOverrideIn,
        *,
        actor_id:       UUID,
        actor_role:     str,
        tenant_id:      UUID,
        schema_name:    str,
        db:             AsyncSession,
    ) -> EligibilityOut:
        row = await HallTicketRepository.get_by_id(eligibility_id, db)
        if not row:
            raise HallTicketServiceError("NOT_FOUND", "Eligibility record not found", 404)

        prev_status = row.status
        row = await HallTicketRepository.apply_override(
            row,
            actor_id   = actor_id,
            new_status = body.status,
            reason     = body.reason,
            db         = db,
        )

        await AuditService.log(
            event_type    = AuditEventType.HUMAN_RATIFICATION,
            actor_user_id = actor_id,
            tenant_id     = tenant_id,
            resource_type = "hall_ticket_eligibility",
            resource_id   = str(eligibility_id),
            action        = "override_eligibility",
            metadata      = {
                "student_id":    str(row.student_id),
                "semester_id":   str(row.semester_id),
                "prev_status":   prev_status,
                "new_status":    body.status,
                "reason_length": len(body.reason),
            },
            schema_name = schema_name,
            db          = db,
        )

        enriched = await HallTicketRepository.list_by_semester(
            semester_id = row.semester_id,
            db          = db,
        )
        match = next((r for r in enriched if r["id"] == row.id), None)
        return _row_to_out(match or {"id": row.id, "student_id": row.student_id,
                                     "semester_id": row.semester_id,
                                     "publish_status": row.publish_status,
                                     "status": row.status,
                                     "computed_at": row.computed_at,
                                     "attendance_threshold_used": row.attendance_threshold_used,
                                     "computed_academic_year": row.computed_academic_year,
                                     "computed_semester_name": row.computed_semester_name,
                                     "attendance_pct": row.attendance_pct,
                                     "has_shortage": row.has_shortage,
                                     "marks_all_locked": row.marks_all_locked,
                                     "marks_all_filled": row.marks_all_filled,
                                     "failure_reasons": row.failure_reasons,
                                     "override_by": row.override_by,
                                     "override_at": row.override_at,
                                     "override_reason": row.override_reason,
                                     "override_status": row.override_status,
                                     "hall_ticket_number": row.hall_ticket_number,
                                     "batch_id": row.batch_id,
                                     "exam_session_id": row.exam_session_id,
                                     "exam_schedule_id": row.exam_schedule_id,
                                     "exam_center_id": row.exam_center_id,
                                     "room_number": row.room_number,
                                     "seat_number": row.seat_number,
                                     "created_at": row.created_at,
                                     "updated_at": row.updated_at,
                                     "student_name": "",
                                     "email": "",
                                     "usn": None})

    # ------------------------------------------------------------------
    # Student self-view
    # ------------------------------------------------------------------

    @staticmethod
    async def my_eligibility(
        *,
        student_id:  UUID,
        semester_id: UUID,
        db:          AsyncSession,
    ) -> MyEligibilityOut:
        row = await HallTicketRepository.get_by_student_semester(student_id, semester_id, db)

        if not row or row.publish_status != PublishStatus.PUBLISHED:
            raise HallTicketServiceError(
                "NOT_PUBLISHED",
                "Eligibility results have not been published yet",
                404,
            )

        meta = await HallTicketRepository.get_semester_meta(semester_id, db)
        sem_name = meta["label"] if meta else row.computed_semester_name

        checklist: list[EligibilityCheckItemOut] = []
        threshold = float(row.attendance_threshold_used)

        att_pct = float(row.attendance_pct) if row.attendance_pct is not None else None
        if att_pct is not None:
            checklist.append(EligibilityCheckItemOut(
                check_name = "Attendance",
                passed     = att_pct >= threshold,
                detail     = f"{att_pct:.1f}% (minimum {threshold:.0f}%)",
            ))
            checklist.append(EligibilityCheckItemOut(
                check_name = "No Attendance Shortage",
                passed     = not row.has_shortage,
                detail     = "No subjects below threshold" if not row.has_shortage
                             else "One or more subjects below threshold",
            ))
        else:
            checklist.append(EligibilityCheckItemOut(
                check_name = "Attendance",
                passed     = True,
                detail     = "No sessions recorded yet (not applicable)",
            ))

        checklist.append(EligibilityCheckItemOut(
            check_name = "Marks Finalized",
            passed     = row.marks_all_locked,
            detail     = "All internal marks components are LOCKED" if row.marks_all_locked
                         else "One or more marks components are not yet finalized",
        ))
        checklist.append(EligibilityCheckItemOut(
            check_name = "Marks Complete",
            passed     = row.marks_all_filled,
            detail     = "All marks entered" if row.marks_all_filled
                         else "Marks not entered for all finalized components",
        ))

        effective_status = row.override_status if row.override_status else row.status
        is_ticket_available = (
            effective_status in (EligibilityStatus.ELIGIBLE, EligibilityStatus.CONDITIONAL)
            and row.hall_ticket_number is not None
        )

        return MyEligibilityOut(
            student_id          = row.student_id,
            student_name        = "",
            usn                 = None,
            semester_id         = row.semester_id,
            semester_name       = sem_name,
            status              = effective_status,
            checklist           = checklist,
            failure_reasons     = row.failure_reasons or [],
            hall_ticket_number  = row.hall_ticket_number,
            is_ticket_available = is_ticket_available,
        )

    # ------------------------------------------------------------------
    # Faculty advisory
    # ------------------------------------------------------------------

    @staticmethod
    async def faculty_advisory(
        *,
        section_id:   UUID,
        semester_id:  UUID,
        faculty_id:   UUID,
        db:           AsyncSession,
    ) -> FacultyAdvisoryOut:
        # Verify faculty is assigned to a course in this section
        __import__("sqlalchemy").text("""
            SELECT 1 FROM subject_assignments sa
            WHERE sa.faculty_user_id = :faculty_id
              AND sa.semester_id     = :semester_id
              AND sa.is_active       = true
            LIMIT 1
        """)
        from sqlalchemy import text as _text
        result = await db.execute(_text("""
            SELECT 1 FROM subject_assignments sa
            JOIN courses c ON c.id = sa.course_id
            JOIN acad_sections sec ON sec.id = (
                SELECT section_id FROM sis_marks_components mc
                WHERE mc.course_id = c.id AND mc.section_id = :section_id
                LIMIT 1
            )
            WHERE sa.faculty_user_id = :faculty_id
              AND sa.semester_id     = :semester_id
              AND sa.is_active       = true
            LIMIT 1
        """), {
            "faculty_id":  str(faculty_id),
            "semester_id": str(semester_id),
            "section_id":  str(section_id),
        })
        if not result.scalar():
            raise HallTicketServiceError(
                "SECTION_NOT_ASSIGNED",
                "You are not assigned to any course in this section",
                403,
            )

        rows = await HallTicketRepository.list_advisory_for_faculty(
            section_id  = section_id,
            semester_id = semester_id,
            db          = db,
        )

        meta = await HallTicketRepository.get_semester_meta(semester_id, db)
        sem_name = meta["label"] if meta else str(semester_id)

        students = [
            AdvisoryStudentRow(
                student_id       = r["student_id"],
                student_name     = r["student_name"],
                usn              = r.get("usn"),
                attendance_pct   = r.get("attendance_pct"),
                has_shortage     = bool(r.get("has_shortage", False)),
                marks_all_locked = bool(r.get("marks_all_locked", False)),
                marks_all_filled = bool(r.get("marks_all_filled", False)),
                status           = r.get("status"),
                publish_status   = r.get("publish_status"),
            )
            for r in rows
        ]

        return FacultyAdvisoryOut(
            section_id    = section_id,
            section_name  = "",
            course_code   = None,
            semester_id   = semester_id,
            semester_name = sem_name,
            students      = students,
        )

    # ------------------------------------------------------------------
    # Generate batch
    # ------------------------------------------------------------------

    @staticmethod
    async def generate_batch(
        body:        HallTicketBatchCreateIn,
        *,
        actor_id:    UUID,
        actor_role:  str,
        tenant_id:   UUID,
        schema_name: str,
        db:          AsyncSession,
    ) -> HallTicketBatchOut:
        meta = await HallTicketRepository.get_semester_meta(body.semester_id, db)
        if not meta:
            raise HallTicketServiceError("SEMESTER_NOT_FOUND", "Semester not found", 404)

        counts = await HallTicketRepository.count_publishable(
            semester_id = body.semester_id,
            section_id  = body.section_id,
            db          = db,
        )
        eligible    = int(counts.get("eligible", 0) or 0)
        conditional = int(counts.get("conditional", 0) or 0)
        total       = eligible + conditional

        if total == 0:
            raise HallTicketServiceError(
                "NO_ELIGIBLE_PUBLISHED",
                "No PUBLISHED ELIGIBLE or CONDITIONAL students found for the given scope. "
                "Publish the eligibility results before generating hall tickets.",
                400,
            )

        # Build ticket prefix: TOCS-{end_year}S{sem_number}
        sem_number  = meta["number"]
        end_year    = meta["end_year"]
        prefix      = f"TOCS-{end_year}S{sem_number}"

        batch = SisHallTicketBatch(
            id            = uuid.uuid4(),
            semester_id   = body.semester_id,
            scope         = BatchScope.SECTION if body.section_id else BatchScope.ALL,
            scope_ref_id  = body.section_id,
            generated_by  = actor_id,
            generated_at  = datetime.now(timezone.utc),
            ticket_count  = 0,
            ticket_prefix = prefix,
            notes         = body.notes,
        )
        batch = await HallTicketRepository.create_batch(batch, db)

        assigned = await HallTicketRepository.assign_hall_tickets(
            semester_id   = body.semester_id,
            section_id    = body.section_id,
            batch_id      = batch.id,
            ticket_prefix = prefix,
            db            = db,
        )

        # Update batch ticket_count
        batch.ticket_count = assigned
        await db.flush()

        await AuditService.log(
            event_type    = AuditEventType.DATA_EXPORT,
            actor_user_id = actor_id,
            tenant_id     = tenant_id,
            resource_type = "hall_ticket_batch",
            resource_id   = str(batch.id),
            action        = "generate_hall_ticket_batch",
            metadata      = {
                "semester_id":  str(body.semester_id),
                "section_id":   str(body.section_id) if body.section_id else None,
                "ticket_count": assigned,
                "ticket_prefix": prefix,
            },
            schema_name = schema_name,
            db          = db,
        )

        return HallTicketBatchOut(
            id            = batch.id,
            semester_id   = batch.semester_id,
            semester_name = meta["label"],
            scope         = batch.scope,
            scope_ref_id  = batch.scope_ref_id,
            generated_by  = batch.generated_by,
            generated_at  = batch.generated_at,
            ticket_count  = assigned,
            ticket_prefix = batch.ticket_prefix,
            notes         = batch.notes,
            created_at    = batch.created_at,
        )

    # ------------------------------------------------------------------
    # List batches
    # ------------------------------------------------------------------

    @staticmethod
    async def list_batches(
        semester_id: Optional[UUID], db: AsyncSession
    ) -> list[HallTicketBatchOut]:
        batches = await HallTicketRepository.list_batches(semester_id, db)
        return [
            HallTicketBatchOut(
                id            = b.id,
                semester_id   = b.semester_id,
                semester_name = None,
                scope         = b.scope,
                scope_ref_id  = b.scope_ref_id,
                generated_by  = b.generated_by,
                generated_at  = b.generated_at,
                ticket_count  = b.ticket_count,
                ticket_prefix = b.ticket_prefix,
                notes         = b.notes,
                created_at    = b.created_at,
            )
            for b in batches
        ]

    # ------------------------------------------------------------------
    # Individual hall ticket (student self-view or Dean/Admin)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_hall_ticket(
        eligibility_id: UUID,
        *,
        requesting_user_id: UUID,
        requesting_role:    str,
        db:                 AsyncSession,
    ) -> HallTicketOut:
        row = await HallTicketRepository.get_by_id(eligibility_id, db)
        if not row:
            raise HallTicketServiceError("NOT_FOUND", "Eligibility record not found", 404)

        # STUDENT can only view their own ticket
        if requesting_role == "STUDENT" and row.student_id != requesting_user_id:
            raise HallTicketServiceError("FORBIDDEN", "Access denied", 403)

        # Ticket must be published and have a number
        if row.publish_status != PublishStatus.PUBLISHED:
            raise HallTicketServiceError("NOT_PUBLISHED", "Hall ticket not yet published", 404)
        if row.hall_ticket_number is None:
            raise HallTicketServiceError("NO_TICKET", "Hall ticket not yet generated", 404)
        if row.status not in (EligibilityStatus.ELIGIBLE, EligibilityStatus.CONDITIONAL):
            raise HallTicketServiceError(
                "NOT_ELIGIBLE",
                "Student is not eligible for a hall ticket",
                400,
            )

        await HallTicketRepository.get_semester_meta(row.semester_id, db)

        return HallTicketOut(
            hall_ticket_number = row.hall_ticket_number,
            student_id         = row.student_id,
            student_name       = "",
            usn                = None,
            semester_id        = row.semester_id,
            semester_name      = row.computed_semester_name,
            academic_year      = row.computed_academic_year,
            status             = row.status,
            batch_id           = row.batch_id,
            issued_at          = row.updated_at or row.created_at,
            exam_session_id    = row.exam_session_id,
            exam_schedule_id   = row.exam_schedule_id,
            exam_center_id     = row.exam_center_id,
            room_number        = row.room_number,
            seat_number        = row.seat_number,
        )
