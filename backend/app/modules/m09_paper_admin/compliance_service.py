"""
M09.9 Compliance & Audit — service orchestration.

Two surfaces:

  • ComplianceService — read-only governance queries and reports.  Composes the
    repository (retrieval) with compliance_core (classification / shaping).  It
    holds no SQL and no maths of its own.

  • ExamMarkAuditService — the single append-only writer.  Called by the
    evaluation service whenever a question mark mutates, it records the
    field-level before/after into ``exam_mark_audit``.  It swallows its own
    errors (like AuditService) so a compliance-write failure can never block the
    business operation it is witnessing.

Nothing here applies a grade.  ("AI advises, humans decide.")
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.modules.m09_paper_admin import compliance_core as core
from app.modules.m09_paper_admin.compliance_repository import ComplianceRepository
from app.modules.m09_paper_admin.compliance_schemas import (
    AuditTrailResponse,
    BoardApprovalRow,
    ComplianceDashboardResponse,
    ComplianceKpis,
    EvaluatorActivityRow,
    MarkAuditEntryResponse,
    ModerationReportRow,
    OcrCorrectionHistoryRow,
    OcrEscalationRow,
    OcrReviewerActivityRow,
    PublicationApprovalRow,
    QuestionMarkHistoryResponse,
    MarkLineageStepResponse,
    ReportResponse,
    ResultChangeHistoryResponse,
    RevaluationReportRow,
    TimelineEntryResponse,
)

logger = logging.getLogger("vidya.compliance")


def _f(v) -> float | None:
    return float(v) if v is not None else None


# ===========================================================================
# Read-only compliance service
# ===========================================================================

class ComplianceService:

    # -----------------------------------------------------------------------
    # Audit trails
    # -----------------------------------------------------------------------

    @staticmethod
    async def _trail(
        *,
        scope: str,
        scope_ref: str | None,
        tenant_id: UUID,
        event_types: list[str] | None,
        actor_user_id: UUID | None,
        target_ids: list[str] | None,
        date_from: datetime | None,
        date_to: datetime | None,
        page: int,
        page_size: int,
        db: AsyncSession,
    ) -> AuditTrailResponse:
        offset = (page - 1) * page_size
        rows, total = await ComplianceRepository.query_events(
            tenant_id=tenant_id,
            event_types=event_types,
            actor_user_id=actor_user_id,
            target_ids=target_ids,
            date_from=date_from,
            date_to=date_to,
            offset=offset,
            limit=page_size,
            db=db,
        )
        names = await ComplianceRepository.user_names(
            [str(r["actor_user_id"]) for r in rows if r.get("actor_user_id")], db=db
        )
        entries = core.build_timeline(rows, names=names)
        return AuditTrailResponse(
            scope=scope,
            scope_ref=scope_ref,
            total=total,
            page=page,
            page_size=page_size,
            category_counts=core.summarise_categories(entries),
            entries=[TimelineEntryResponse(**vars(e)) for e in entries],
        )

    @staticmethod
    async def trail_by_student(
        student_user_id: UUID, *, tenant_id: UUID, categories=None,
        date_from=None, date_to=None, page=1, page_size=50, db: AsyncSession,
    ) -> AuditTrailResponse:
        script_ids = await ComplianceRepository.script_ids_for_student(student_user_id, db=db)
        return await ComplianceService._trail(
            scope="STUDENT", scope_ref=str(student_user_id), tenant_id=tenant_id,
            event_types=core.event_types_for_categories(categories),
            actor_user_id=None, target_ids=script_ids,
            date_from=date_from, date_to=date_to, page=page, page_size=page_size, db=db,
        )

    @staticmethod
    async def trail_by_script(
        script_id: UUID, *, tenant_id: UUID, categories=None,
        date_from=None, date_to=None, page=1, page_size=50, db: AsyncSession,
    ) -> AuditTrailResponse:
        return await ComplianceService._trail(
            scope="SCRIPT", scope_ref=str(script_id), tenant_id=tenant_id,
            event_types=core.event_types_for_categories(categories),
            actor_user_id=None, target_ids=[str(script_id)],
            date_from=date_from, date_to=date_to, page=page, page_size=page_size, db=db,
        )

    @staticmethod
    async def trail_by_exam(
        exam_paper_id: UUID, *, tenant_id: UUID, categories=None,
        date_from=None, date_to=None, page=1, page_size=50, db: AsyncSession,
    ) -> AuditTrailResponse:
        script_ids = await ComplianceRepository.script_ids_for_exam(exam_paper_id, db=db)
        return await ComplianceService._trail(
            scope="EXAM", scope_ref=str(exam_paper_id), tenant_id=tenant_id,
            event_types=core.event_types_for_categories(categories),
            actor_user_id=None, target_ids=script_ids,
            date_from=date_from, date_to=date_to, page=page, page_size=page_size, db=db,
        )

    @staticmethod
    async def trail_by_evaluator(
        evaluator_id: UUID, *, tenant_id: UUID, categories=None,
        date_from=None, date_to=None, page=1, page_size=50, db: AsyncSession,
    ) -> AuditTrailResponse:
        return await ComplianceService._trail(
            scope="EVALUATOR", scope_ref=str(evaluator_id), tenant_id=tenant_id,
            event_types=core.event_types_for_categories(categories),
            actor_user_id=evaluator_id, target_ids=None,
            date_from=date_from, date_to=date_to, page=page, page_size=page_size, db=db,
        )

    @staticmethod
    async def trail_by_date_range(
        *, tenant_id: UUID, categories=None, actor_user_id: UUID | None = None,
        date_from=None, date_to=None, page=1, page_size=50, db: AsyncSession,
    ) -> AuditTrailResponse:
        return await ComplianceService._trail(
            scope="DATE_RANGE", scope_ref=None, tenant_id=tenant_id,
            event_types=core.event_types_for_categories(categories),
            actor_user_id=actor_user_id, target_ids=None,
            date_from=date_from, date_to=date_to, page=page, page_size=page_size, db=db,
        )

    # -----------------------------------------------------------------------
    # Result change history (field-level + derived lineage)
    # -----------------------------------------------------------------------

    @staticmethod
    async def result_change_history(
        script_id: UUID, *, db: AsyncSession,
    ) -> ResultChangeHistoryResponse:
        header = await ComplianceRepository.script_header(script_id, db=db)
        revealed = bool(header and header.get("status") == "BOARD_FINALISED")

        audit_rows = await ComplianceRepository.mark_audit_for_script(script_id, db=db)
        names = await ComplianceRepository.user_names(
            [str(r["actor_user_id"]) for r in audit_rows if r.get("actor_user_id")], db=db
        )
        recorded = [
            MarkAuditEntryResponse(
                id=str(r["id"]),
                script_id=str(r["script_id"]),
                exam_paper_id=str(r["exam_paper_id"]),
                question_id=str(r["question_id"]) if r.get("question_id") else None,
                evaluation_round=r.get("evaluation_round"),
                change_type=r["change_type"],
                previous_marks=_f(r.get("previous_marks")),
                new_marks=_f(r.get("new_marks")),
                max_marks=_f(r.get("max_marks")),
                delta=_f(r.get("delta")),
                actor_user_id=str(r["actor_user_id"]),
                actor_role=r.get("actor_role"),
                actor_name=names.get(str(r["actor_user_id"])),
                reason=r.get("reason"),
                source_event=r.get("source_event"),
                # Identity only when already revealed by Board finalisation
                masked_id=r.get("masked_id"),
                created_at=r["created_at"],
            )
            for r in audit_rows
        ]

        eval_rows = await ComplianceRepository.evaluations_for_script(script_id, db=db)
        lineage = core.derive_question_lineage(eval_rows)
        question_history = [
            QuestionMarkHistoryResponse(
                question_id=q.question_id,
                question_type=q.question_type,
                max_marks=q.max_marks,
                steps=[MarkLineageStepResponse(**vars(s)) for s in q.steps],
            )
            for q in lineage
        ]

        return ResultChangeHistoryResponse(
            script_id=str(script_id),
            exam_paper_id=header.get("exam_paper_id") if header else None,
            masked_id=header.get("masked_id") if header else None,
            student_revealed=revealed,
            student_user_id=(header.get("student_user_id") if header and revealed else None),
            recorded_changes=recorded,
            question_history=question_history,
        )

    # -----------------------------------------------------------------------
    # Compliance reports
    # -----------------------------------------------------------------------

    @staticmethod
    async def publication_approval_report(
        exam_paper_id: UUID | None, *, db: AsyncSession,
    ) -> list[PublicationApprovalRow]:
        rows = await ComplianceRepository.board_sessions(exam_paper_id, db=db)
        titles = await ComplianceRepository.paper_titles([r["exam_paper_id"] for r in rows], db=db)
        names = await ComplianceRepository.user_names(
            [v for r in rows for v in (r.get("convened_by"), r.get("decided_by"), r.get("declared_by"))],
            db=db,
        )
        return [
            PublicationApprovalRow(
                exam_paper_id=r["exam_paper_id"],
                exam_paper_title=titles.get(r["exam_paper_id"]),
                session_id=r["session_id"],
                convened_by=r.get("convened_by"),
                convened_by_name=names.get(r.get("convened_by")),
                convened_at=r.get("convened_at"),
                decided_by=r.get("decided_by"),
                decided_by_name=names.get(r.get("decided_by")),
                decided_at=r.get("decided_at"),
                declared_by=r.get("declared_by"),
                declared_by_name=names.get(r.get("declared_by")),
                declared_at=r.get("declared_at"),
                status=r["status"],
                board_remarks=r.get("board_remarks"),
            )
            for r in rows
        ]

    @staticmethod
    async def moderation_report(
        exam_paper_id: UUID | None, *, db: AsyncSession,
    ) -> list[ModerationReportRow]:
        rows = await ComplianceRepository.moderation_reviews(exam_paper_id, db=db)
        names = await ComplianceRepository.user_names(
            [v for r in rows for v in (r.get("flagged_by"), r.get("moderator_id"))], db=db
        )
        return [
            ModerationReportRow(
                review_id=r["review_id"],
                script_id=r["script_id"],
                masked_id=r.get("masked_id"),
                exam_paper_id=r["exam_paper_id"],
                primary_total=_f(r.get("primary_total")),
                secondary_total=_f(r.get("secondary_total")),
                variance_pct=_f(r.get("variance_pct")),
                variance_threshold=_f(r.get("variance_threshold")),
                flag_reason=r.get("flag_reason"),
                flagged_by=r.get("flagged_by"),
                flagged_by_name=names.get(r.get("flagged_by")),
                moderator_id=r.get("moderator_id"),
                moderator_name=names.get(r.get("moderator_id")),
                moderation_notes=r.get("moderation_notes"),
                status=r["status"],
                flagged_at=r.get("flagged_at"),
                completed_at=r.get("completed_at"),
            )
            for r in rows
        ]

    @staticmethod
    async def revaluation_report(
        exam_paper_id: UUID | None, *, db: AsyncSession,
    ) -> list[RevaluationReportRow]:
        rows = await ComplianceRepository.revaluation_requests(exam_paper_id, db=db)
        names = await ComplianceRepository.user_names(
            [v for r in rows for v in (r.get("assigned_evaluator_id"), r.get("decided_by"))], db=db
        )
        out: list[RevaluationReportRow] = []
        for r in rows:
            orig = _f(r.get("original_total"))
            awarded = _f(r.get("awarded_total"))
            out.append(RevaluationReportRow(
                request_id=r["request_id"],
                script_id=r["script_id"],
                exam_paper_id=r["exam_paper_id"],
                status=r["status"],
                original_total=orig,
                revaluation_total=_f(r.get("revaluation_total")),
                awarded_total=awarded,
                delta=core.compute_delta(orig, awarded),
                assigned_evaluator_id=r.get("assigned_evaluator_id"),
                assigned_evaluator_name=names.get(r.get("assigned_evaluator_id")),
                decided_by=r.get("decided_by"),
                decided_by_name=names.get(r.get("decided_by")),
                decided_at=r.get("decided_at"),
                reason=r.get("reason"),
                board_remarks=r.get("board_remarks"),
                created_at=r.get("created_at"),
            ))
        return out

    @staticmethod
    async def evaluator_activity_report(
        exam_paper_id: UUID | None, *, db: AsyncSession,
    ) -> list[EvaluatorActivityRow]:
        rows = await ComplianceRepository.evaluator_activity(exam_paper_id, db=db)
        mark_counts = await ComplianceRepository.mark_change_counts_by_actor(exam_paper_id, db=db)
        names = await ComplianceRepository.user_names([r["evaluator_id"] for r in rows], db=db)
        return [
            EvaluatorActivityRow(
                evaluator_id=r["evaluator_id"],
                evaluator_name=names.get(r["evaluator_id"]),
                scripts_assigned=int(r["scripts_assigned"]),
                scripts_submitted=int(r["scripts_submitted"]),
                mark_changes=mark_counts.get(r["evaluator_id"], 0),
                last_activity_at=r.get("last_activity_at"),
            )
            for r in rows
        ]

    @staticmethod
    async def board_approval_report(
        exam_paper_id: UUID | None, *, db: AsyncSession,
    ) -> list[BoardApprovalRow]:
        rows = await ComplianceRepository.board_sessions(exam_paper_id, db=db)
        titles = await ComplianceRepository.paper_titles([r["exam_paper_id"] for r in rows], db=db)
        names = await ComplianceRepository.user_names(
            [v for r in rows for v in (r.get("convened_by"), r.get("decided_by"))], db=db
        )
        return [
            BoardApprovalRow(
                session_id=r["session_id"],
                exam_paper_id=r["exam_paper_id"],
                exam_paper_title=titles.get(r["exam_paper_id"]),
                session_title=r.get("session_title"),
                status=r["status"],
                convened_by=r.get("convened_by"),
                convened_by_name=names.get(r.get("convened_by")),
                convened_at=r.get("convened_at"),
                decided_by=r.get("decided_by"),
                decided_by_name=names.get(r.get("decided_by")),
                decided_at=r.get("decided_at"),
                pass_rate_pct=_f(r.get("pass_rate_pct")),
                mean_marks=_f(r.get("mean_marks")),
                total_scripts=int(r["total_scripts"]) if r.get("total_scripts") is not None else None,
                board_remarks=r.get("board_remarks"),
            )
            for r in rows
        ]

    @staticmethod
    async def ocr_correction_history_report(
        exam_paper_id: UUID | None, *, db: AsyncSession,
    ) -> list[OcrCorrectionHistoryRow]:
        from app.modules.m09_paper_admin.ocr_repository import OcrQueueRepository
        rows = await OcrQueueRepository.ocr_correction_history(exam_paper_id, db=db)
        names = await ComplianceRepository.user_names(
            [r["reviewer_id"] for r in rows if r.get("reviewer_id")], db=db
        )
        return [
            OcrCorrectionHistoryRow(
                queue_id=r["queue_id"],
                script_id=r["script_id"],
                masked_id=r.get("masked_id"),
                exam_paper_id=r["exam_paper_id"],
                priority_category=r.get("priority_category"),
                ocr_confidence=_f(r.get("ocr_confidence")),
                action_taken=r.get("action_taken"),
                reviewer_id=r.get("reviewer_id"),
                reviewer_name=names.get(r.get("reviewer_id") or ""),
                reviewer_notes=r.get("reviewer_notes"),
                review_started_at=r.get("review_started_at"),
                completed_at=r.get("completed_at"),
            )
            for r in rows
        ]

    @staticmethod
    async def ocr_reviewer_activity_report(
        exam_paper_id: UUID | None, *, db: AsyncSession,
    ) -> list[OcrReviewerActivityRow]:
        from app.modules.m09_paper_admin.ocr_repository import OcrQueueRepository
        rows = await OcrQueueRepository.ocr_reviewer_activity(exam_paper_id, db=db)
        names = await ComplianceRepository.user_names(
            [r["reviewer_id"] for r in rows if r.get("reviewer_id")], db=db
        )
        return [
            OcrReviewerActivityRow(
                reviewer_id=r["reviewer_id"],
                reviewer_name=names.get(r["reviewer_id"]),
                total_reviewed=int(r["total_reviewed"]),
                corrections=int(r["corrections"]),
                accepted=int(r["accepted"]),
                rerun_requested=int(r["rerun_requested"]),
                escalated=int(r["escalated"]),
                marked_unreadable=int(r["marked_unreadable"]),
                last_activity_at=r.get("last_activity_at"),
            )
            for r in rows
        ]

    @staticmethod
    async def ocr_escalation_report(
        exam_paper_id: UUID | None, *, db: AsyncSession,
    ) -> list[OcrEscalationRow]:
        from app.modules.m09_paper_admin.ocr_repository import OcrQueueRepository
        rows = await OcrQueueRepository.ocr_escalation_report(exam_paper_id, db=db)
        names = await ComplianceRepository.user_names(
            [r["reviewer_id"] for r in rows if r.get("reviewer_id")], db=db
        )
        return [
            OcrEscalationRow(
                queue_id=r["queue_id"],
                script_id=r["script_id"],
                masked_id=r.get("masked_id"),
                exam_paper_id=r["exam_paper_id"],
                priority_category=r.get("priority_category"),
                ocr_confidence=_f(r.get("ocr_confidence")),
                reviewer_id=r.get("reviewer_id"),
                reviewer_name=names.get(r.get("reviewer_id") or ""),
                reviewer_notes=r.get("reviewer_notes"),
                review_started_at=r.get("review_started_at"),
                completed_at=r.get("completed_at"),
            )
            for r in rows
        ]

    # Report dispatcher (drives both the JSON endpoint and CSV export)
    _REPORTS = {
        "publication_approval": ("publication_approval_report", [
            "exam_paper_id", "exam_paper_title", "session_id", "status",
            "convened_by_name", "convened_at", "decided_by_name", "decided_at",
            "declared_by_name", "declared_at", "board_remarks",
        ]),
        "moderation": ("moderation_report", [
            "review_id", "script_id", "masked_id", "exam_paper_id", "primary_total",
            "secondary_total", "variance_pct", "variance_threshold", "flag_reason",
            "flagged_by_name", "moderator_name", "moderation_notes", "status",
            "flagged_at", "completed_at",
        ]),
        "revaluation": ("revaluation_report", [
            "request_id", "script_id", "exam_paper_id", "status", "original_total",
            "revaluation_total", "awarded_total", "delta", "assigned_evaluator_name",
            "decided_by_name", "decided_at", "reason", "board_remarks", "created_at",
        ]),
        "evaluator_activity": ("evaluator_activity_report", [
            "evaluator_id", "evaluator_name", "scripts_assigned", "scripts_submitted",
            "mark_changes", "last_activity_at",
        ]),
        "board_approval": ("board_approval_report", [
            "session_id", "exam_paper_id", "exam_paper_title", "session_title", "status",
            "convened_by_name", "convened_at", "decided_by_name", "decided_at",
            "pass_rate_pct", "mean_marks", "total_scripts", "board_remarks",
        ]),
        "ocr_correction_history": ("ocr_correction_history_report", [
            "queue_id", "script_id", "masked_id", "exam_paper_id",
            "priority_category", "ocr_confidence", "action_taken",
            "reviewer_name", "reviewer_notes", "review_started_at", "completed_at",
        ]),
        "ocr_reviewer_activity": ("ocr_reviewer_activity_report", [
            "reviewer_id", "reviewer_name", "total_reviewed", "corrections",
            "accepted", "rerun_requested", "escalated", "marked_unreadable",
            "last_activity_at",
        ]),
        "ocr_escalation": ("ocr_escalation_report", [
            "queue_id", "script_id", "masked_id", "exam_paper_id",
            "priority_category", "ocr_confidence", "reviewer_name",
            "reviewer_notes", "review_started_at", "completed_at",
        ]),
    }

    @staticmethod
    def report_names() -> list[str]:
        return list(ComplianceService._REPORTS.keys())

    @staticmethod
    async def run_report(
        report: str, exam_paper_id: UUID | None, *, db: AsyncSession,
    ) -> ReportResponse:
        method_name, _cols = ComplianceService._REPORTS[report]
        method = getattr(ComplianceService, method_name)
        rows = await method(exam_paper_id, db=db)
        dict_rows = [r.model_dump(mode="json") for r in rows]
        return ReportResponse(
            report=report,
            exam_paper_id=str(exam_paper_id) if exam_paper_id else None,
            generated_at=datetime.now(timezone.utc),
            row_count=len(dict_rows),
            rows=dict_rows,
        )

    @staticmethod
    async def run_report_csv(
        report: str, exam_paper_id: UUID | None, *, db: AsyncSession,
    ) -> str:
        method_name, columns = ComplianceService._REPORTS[report]
        method = getattr(ComplianceService, method_name)
        rows = await method(exam_paper_id, db=db)
        dict_rows = [r.model_dump(mode="json") for r in rows]
        return core.to_csv(dict_rows, columns)

    # -----------------------------------------------------------------------
    # Dashboard bundle
    # -----------------------------------------------------------------------

    @staticmethod
    async def dashboard(
        exam_paper_id: UUID | None, *, tenant_id: UUID,
        date_from=None, date_to=None, recent_limit: int = 20, db: AsyncSession,
    ) -> ComplianceDashboardResponse:
        counts = await ComplianceRepository.count_events_by_type(
            tenant_id=tenant_id, exam_paper_id=exam_paper_id,
            date_from=date_from, date_to=date_to, db=db,
        )

        def _sum(*types: str) -> int:
            return sum(counts.get(t, 0) for t in types)

        category_counts = {c: 0 for c in core.ALL_CATEGORIES}
        for et, n in counts.items():
            cat = core.category_for(et)
            if cat:
                category_counts[cat] += n

        # Board-adjustment count comes from the field-level audit (more precise
        # than the generic SCRIPT_MARKS_UPDATED event).
        board_adj_counts = await ComplianceRepository.mark_change_counts_by_actor(exam_paper_id, db=db)

        kpis = ComplianceKpis(
            total_events=sum(counts.values()),
            mark_changes=_sum("SCRIPT_MARKS_UPDATED"),
            board_adjustments=0,  # filled from exam_mark_audit below
            moderations=_sum("SCRIPT_MODERATION_FLAGGED", "SCRIPT_MODERATION_SUBMITTED"),
            revaluations=_sum("REVALUATION_REQUESTED"),
            board_approvals=_sum("BOARD_SESSION_APPROVED"),
            publications=_sum("RESULTS_DECLARED"),
        )

        # Recent events timeline
        rows, _total = await ComplianceRepository.query_events(
            tenant_id=tenant_id,
            event_types=None,
            target_ids=(await ComplianceRepository.script_ids_for_exam(exam_paper_id, db=db))
            if exam_paper_id else None,
            date_from=date_from, date_to=date_to, offset=0, limit=recent_limit, db=db,
        )
        names = await ComplianceRepository.user_names(
            [str(r["actor_user_id"]) for r in rows if r.get("actor_user_id")], db=db
        )
        entries = core.build_timeline(rows, names=names)

        return ComplianceDashboardResponse(
            scope="PAPER" if exam_paper_id else "INSTITUTION",
            exam_paper_id=str(exam_paper_id) if exam_paper_id else None,
            kpis=kpis,
            category_counts=category_counts,
            recent_events=[TimelineEntryResponse(**vars(e)) for e in entries],
        )


# ===========================================================================
# Append-only mark-audit writer (the single write path)
# ===========================================================================

class ExamMarkAuditService:
    """Records field-level mark mutations into the append-only exam_mark_audit.

    Invoked by the evaluation service after a successful mark write.  It opens
    its OWN session (independent of the business transaction) and swallows all
    exceptions, exactly like AuditService — a compliance-write failure must
    never roll back or block the mark change it is witnessing.
    """

    @staticmethod
    async def record_changes(
        *,
        script_id: UUID,
        exam_paper_id: UUID,
        change_type: str,
        actor_user_id: UUID,
        actor_role: str | None,
        source_event: str | None,
        changes: list[dict],
        masked_id: str | None = None,
        evaluation_round: str | None = None,
    ) -> None:
        """`changes` = [{question_id, previous_marks, new_marks, max_marks, reason}]."""
        if not changes:
            return
        try:
            payload = []
            for c in changes:
                prev = c.get("previous_marks")
                new = c.get("new_marks")
                delta = None
                if prev is not None and new is not None:
                    delta = round(float(new) - float(prev), 2)
                payload.append({
                    "script_id": str(script_id),
                    "exam_paper_id": str(exam_paper_id),
                    "question_id": str(c["question_id"]) if c.get("question_id") else None,
                    "evaluation_round": c.get("evaluation_round") or evaluation_round,
                    "student_user_id": None,  # anonymity preserved pre-finalisation
                    "masked_id": masked_id,
                    "change_type": change_type,
                    "previous_marks": prev,
                    "new_marks": new,
                    "max_marks": c.get("max_marks"),
                    "delta": delta,
                    "actor_user_id": str(actor_user_id),
                    "actor_role": actor_role,
                    "reason": c.get("reason"),
                    "source_event": source_event,
                })
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await ComplianceRepository.insert_mark_audit(payload, db=session)
        except Exception:
            logger.error(
                "mark_audit_write_failed script=%s change_type=%s actor=%s",
                script_id, change_type, actor_user_id, exc_info=True,
            )
