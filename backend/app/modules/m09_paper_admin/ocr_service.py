"""
M09.7 OCR Review Queue — service layer.

Two service classes:

  OcrThresholdService — manages configurable confidence thresholds.
    Admin-only write; institution-wide read.

  OcrReviewService — manages the human OCR review workflow.
    Enqueue (called internally after OCR pipeline); review actions (human gates).
    All terminal actions emit audit events. No action here changes script marks.
    ("AI advises, humans decide.")

Human-gate invariants:
  - accept() / correct() / rerun() / escalate() / unreadable() may only be
    called on a queue item that is PENDING or IN_REVIEW.
  - Only one active (PENDING / IN_REVIEW) queue entry exists per script at a time.
  - corrected_text is written ONLY by the correct() action.
  - No evaluator_marks or script status is modified by any method here.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    # Used only in the string return annotation on _get_active.
    from app.modules.m09_paper_admin.ocr_models import OcrReviewQueue

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.schemas import CurrentUser
from app.modules.m09_paper_admin.ocr_models import (
    OcrPriorityCategory,
    OcrReviewStatus,
)
from app.modules.m09_paper_admin.ocr_repository import (
    OcrQueueRepository,
    OcrThresholdRepository,
)
from app.modules.m09_paper_admin.ocr_schemas import (
    EffectiveThresholdResponse,
    OcrActionResponse,
    OcrDashboardResponse,
    OcrQueueItem,
    OcrQueueListResponse,
    OcrReviewDetailResponse,
    OcrThresholdResponse,
)

logger = logging.getLogger("vidya.m09.ocr")


class OcrServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code        = code
        self.message     = message
        self.status_code = status_code


def _f(v) -> float | None:
    return float(v) if v is not None else None


# ===========================================================================
# Threshold service
# ===========================================================================

class OcrThresholdService:

    @staticmethod
    async def get_effective(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> EffectiveThresholdResponse:
        """Return the most specific active threshold (EXAM > GLOBAL)."""
        override = None
        if exam_paper_id:
            override = await OcrThresholdRepository.get_exam_override(exam_paper_id, db=db)

        if override:
            return EffectiveThresholdResponse(
                low_confidence_threshold=float(override.low_confidence_threshold),
                medium_confidence_threshold=float(override.medium_confidence_threshold),
                source_scope="EXAM",
                source_id=str(exam_paper_id),
            )

        global_cfg = await OcrThresholdRepository.get_global(db=db)
        if global_cfg:
            return EffectiveThresholdResponse(
                low_confidence_threshold=float(global_cfg.low_confidence_threshold),
                medium_confidence_threshold=float(global_cfg.medium_confidence_threshold),
                source_scope="GLOBAL",
            )
        # Hard fallback if no config row exists (migration seeds one, but be defensive)
        return EffectiveThresholdResponse(
            low_confidence_threshold=0.60,
            medium_confidence_threshold=0.80,
            source_scope="GLOBAL",
        )

    @staticmethod
    async def set_threshold(
        scope: str,
        scope_ref_id: UUID | None,
        low_threshold: float,
        medium_threshold: float,
        current_user: CurrentUser,
        *,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> OcrThresholdResponse:
        if low_threshold >= medium_threshold:
            raise OcrServiceError(
                "INVALID_THRESHOLD",
                "low_confidence_threshold must be strictly less than medium_confidence_threshold.",
            )
        row = await OcrThresholdRepository.upsert(
            scope=scope,
            scope_ref_id=scope_ref_id,
            low_threshold=low_threshold,
            medium_threshold=medium_threshold,
            created_by=current_user.id,
            db=db,
        )
        await AuditService.log(
            event_type=AuditEventType.OCR_THRESHOLD_UPDATED,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            tenant_id=tenant_id,
            target_entity="ocr_threshold_config",
            target_id=row.id,
            metadata={
                "scope": scope,
                "scope_ref_id": str(scope_ref_id) if scope_ref_id else None,
                "low_confidence_threshold": float(low_threshold),
                "medium_confidence_threshold": float(medium_threshold),
            },
        )
        return OcrThresholdResponse.model_validate(row)

    @staticmethod
    async def list_all(*, db: AsyncSession) -> list[OcrThresholdResponse]:
        rows = await OcrThresholdRepository.list_all(db=db)
        return [OcrThresholdResponse.model_validate(r) for r in rows]


# ===========================================================================
# Review service
# ===========================================================================

class OcrReviewService:

    # -----------------------------------------------------------------------
    # Enqueue (called from OCR pipeline / quality detector)
    # -----------------------------------------------------------------------

    @staticmethod
    async def enqueue_if_needed(
        script_id: UUID,
        exam_paper_id: UUID,
        ocr_status: str | None,
        ocr_text: str | None,
        ocr_confidence: float | None,
        scan_quality_flags: list[dict] | None,
        *,
        db: AsyncSession,
    ) -> bool:
        """
        Evaluate whether a script needs OCR human review and, if so, enqueue it.

        Called after the OCR pipeline completes. Returns True if enqueued.
        Never raises — all failures are logged and swallowed so the OCR pipeline
        is not blocked.
        """
        try:
            threshold = await OcrThresholdService.get_effective(exam_paper_id, db=db)

            category = OcrReviewService._classify(
                ocr_status=ocr_status,
                ocr_confidence=ocr_confidence,
                scan_quality_flags=scan_quality_flags,
                low_threshold=threshold.low_confidence_threshold,
                medium_threshold=threshold.medium_confidence_threshold,
            )
            if category is None:
                return False

            await OcrQueueRepository.enqueue(
                script_id=script_id,
                exam_paper_id=exam_paper_id,
                priority_category=category,
                original_ocr_text=ocr_text,
                ocr_confidence=ocr_confidence,
                db=db,
            )
            return True
        except Exception as exc:
            logger.warning("OCR enqueue failed for script %s: %s", script_id, exc)
            return False

    @staticmethod
    def _classify(
        *,
        ocr_status: str | None,
        ocr_confidence: float | None,
        scan_quality_flags: list[dict] | None,
        low_threshold: float,
        medium_threshold: float,
    ) -> OcrPriorityCategory | None:
        """Determine the priority category. None = no review needed."""
        if ocr_status in ("FAILED", "ERROR") or (
            ocr_confidence is None and ocr_status not in ("PENDING", "PROCESSING")
        ):
            return OcrPriorityCategory.OCR_FAILURE

        if ocr_confidence is not None and ocr_confidence < low_threshold:
            return OcrPriorityCategory.LOW_CONFIDENCE

        flags = scan_quality_flags or []
        has_critical_flag = any(
            f.get("severity") in ("CRITICAL", "HIGH") for f in flags
        )
        if has_critical_flag:
            return OcrPriorityCategory.QUALITY_ISSUE

        if ocr_confidence is not None and ocr_confidence < medium_threshold:
            return OcrPriorityCategory.MEDIUM_CONFIDENCE

        return None

    # -----------------------------------------------------------------------
    # Queue read
    # -----------------------------------------------------------------------

    @staticmethod
    async def get_queue(
        *,
        exam_paper_id: UUID | None = None,
        priority_category: str | None = None,
        show_completed: bool = False,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> OcrQueueListResponse:
        statuses = None
        if not show_completed:
            statuses = [OcrReviewStatus.PENDING, OcrReviewStatus.IN_REVIEW]

        rows, total = await OcrQueueRepository.list_queue(
            exam_paper_id=exam_paper_id,
            priority_category=priority_category,
            review_status=statuses,
            offset=offset,
            limit=limit,
            db=db,
        )
        # Enrich with masked_id from scanned_scripts via raw SQL
        if rows:
            from sqlalchemy import text
            ids = [str(r.script_id) for r in rows]
            masked = (await db.execute(
                text(
                    "SELECT id::text AS id, masked_id FROM scanned_scripts "
                    "WHERE id = ANY(:ids)"
                ),
                {"ids": ids},
            )).mappings().all()
            masked_map = {m["id"]: m["masked_id"] for m in masked}
        else:
            masked_map = {}

        items = []
        for r in rows:
            item = OcrQueueItem(
                id=r.id,
                script_id=r.script_id,
                exam_paper_id=r.exam_paper_id,
                masked_id=masked_map.get(str(r.script_id)),
                priority_category=r.priority_category,
                priority_score=r.priority_score,
                ocr_confidence=_f(r.ocr_confidence),
                review_status=r.review_status,
                assigned_reviewer_id=r.assigned_reviewer_id,
                review_started_at=r.review_started_at,
                action_taken=r.action_taken,
                completed_at=r.completed_at,
                created_at=r.created_at,
            )
            items.append(item)
        return OcrQueueListResponse(items=items, total=total, offset=offset, limit=limit)

    @staticmethod
    async def get_detail(
        queue_id: UUID,
        *,
        db: AsyncSession,
    ) -> OcrReviewDetailResponse:
        from sqlalchemy import text
        row = await OcrQueueRepository.get_by_id(queue_id, db=db)
        if not row:
            raise OcrServiceError("NOT_FOUND", "OCR review queue item not found.", 404)

        script = (await db.execute(
            text(
                "SELECT masked_id, ocr_status, ocr_text, ocr_quality_score, "
                "       scan_quality_flags, page_count, page_image_keys "
                "FROM scanned_scripts WHERE id = CAST(:sid AS uuid)"
            ),
            {"sid": str(row.script_id)},
        )).mappings().first()

        return OcrReviewDetailResponse(
            queue_id=row.id,
            script_id=row.script_id,
            exam_paper_id=row.exam_paper_id,
            masked_id=script["masked_id"] if script else None,
            priority_category=row.priority_category,
            priority_score=row.priority_score,
            review_status=row.review_status,
            original_ocr_text=row.original_ocr_text,
            ocr_confidence=_f(row.ocr_confidence),
            corrected_text=row.corrected_text,
            ocr_status=script["ocr_status"] if script else None,
            ocr_quality_score=_f(script["ocr_quality_score"]) if script else None,
            scan_quality_flags=script["scan_quality_flags"] if script else None,
            page_count=script["page_count"] if script else None,
            page_image_keys=script["page_image_keys"] if script else None,
            assigned_reviewer_id=row.assigned_reviewer_id,
            review_started_at=row.review_started_at,
            reviewer_notes=row.reviewer_notes,
            action_taken=row.action_taken,
            completed_by=row.completed_by,
            completed_at=row.completed_at,
            created_at=row.created_at,
        )

    @staticmethod
    async def get_dashboard(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> OcrDashboardResponse:
        counts = await OcrQueueRepository.dashboard_counts(exam_paper_id=exam_paper_id, db=db)
        return OcrDashboardResponse(
            pending_total=int(counts.get("pending_total") or 0),
            in_review_total=int(counts.get("in_review_total") or 0),
            ocr_failure_count=int(counts.get("ocr_failure_count") or 0),
            low_confidence_count=int(counts.get("low_confidence_count") or 0),
            quality_issue_count=int(counts.get("quality_issue_count") or 0),
            medium_confidence_count=int(counts.get("medium_confidence_count") or 0),
            completed_today=int(counts.get("completed_today") or 0),
        )

    # -----------------------------------------------------------------------
    # Review actions (human gates)
    # -----------------------------------------------------------------------

    @staticmethod
    async def _get_active(queue_id: UUID, *, db: AsyncSession) -> "OcrReviewQueue":
        row = await OcrQueueRepository.get_by_id(queue_id, db=db)
        if not row:
            raise OcrServiceError("NOT_FOUND", "OCR queue item not found.", 404)
        if row.review_status not in (OcrReviewStatus.PENDING, OcrReviewStatus.IN_REVIEW):
            raise OcrServiceError(
                "ALREADY_COMPLETED",
                f"Queue item is already in terminal status '{row.review_status}'.",
                409,
            )
        return row

    @staticmethod
    async def start_review(
        queue_id: UUID,
        current_user: CurrentUser,
        *,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> OcrActionResponse:
        row = await OcrReviewService._get_active(queue_id, db=db)
        row = await OcrQueueRepository.set_in_review(queue_id, current_user.id, db=db)
        await AuditService.log(
            event_type=AuditEventType.OCR_REVIEW_STARTED,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            tenant_id=tenant_id,
            target_entity="ocr_review_queue",
            target_id=queue_id,
            metadata={"script_id": str(row.script_id)},
        )
        return OcrActionResponse(
            queue_id=row.id,
            script_id=row.script_id,
            review_status=row.review_status,
            action_taken=None,
            completed_at=None,
            message="Review started.",
        )

    @staticmethod
    async def accept(
        queue_id: UUID,
        reviewer_notes: str | None,
        current_user: CurrentUser,
        *,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> OcrActionResponse:
        await OcrReviewService._get_active(queue_id, db=db)
        row = await OcrQueueRepository.complete_review(
            queue_id=queue_id,
            new_status=OcrReviewStatus.ACCEPTED,
            action_taken="ACCEPTED",
            completed_by=current_user.id,
            reviewer_notes=reviewer_notes,
            db=db,
        )
        await AuditService.log(
            event_type=AuditEventType.OCR_ACCEPTED,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            tenant_id=tenant_id,
            target_entity="ocr_review_queue",
            target_id=queue_id,
            metadata={"script_id": str(row.script_id)},
        )
        return OcrActionResponse(
            queue_id=row.id, script_id=row.script_id,
            review_status=row.review_status, action_taken=row.action_taken,
            completed_at=row.completed_at, message="OCR text accepted.",
        )

    @staticmethod
    async def correct(
        queue_id: UUID,
        corrected_text: str,
        reviewer_notes: str | None,
        current_user: CurrentUser,
        *,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> OcrActionResponse:
        await OcrReviewService._get_active(queue_id, db=db)
        row = await OcrQueueRepository.complete_review(
            queue_id=queue_id,
            new_status=OcrReviewStatus.CORRECTED,
            action_taken="CORRECTED",
            completed_by=current_user.id,
            corrected_text=corrected_text,
            reviewer_notes=reviewer_notes,
            db=db,
        )
        await AuditService.log(
            event_type=AuditEventType.OCR_TEXT_CORRECTED,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            tenant_id=tenant_id,
            target_entity="ocr_review_queue",
            target_id=queue_id,
            metadata={
                "script_id": str(row.script_id),
                "text_length": len(corrected_text),
            },
        )
        return OcrActionResponse(
            queue_id=row.id, script_id=row.script_id,
            review_status=row.review_status, action_taken=row.action_taken,
            completed_at=row.completed_at, message="OCR text corrected and saved.",
        )

    @staticmethod
    async def request_rerun(
        queue_id: UUID,
        reviewer_notes: str | None,
        current_user: CurrentUser,
        *,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> OcrActionResponse:
        await OcrReviewService._get_active(queue_id, db=db)
        row = await OcrQueueRepository.complete_review(
            queue_id=queue_id,
            new_status=OcrReviewStatus.RERUN_REQUESTED,
            action_taken="RERUN_REQUESTED",
            completed_by=current_user.id,
            reviewer_notes=reviewer_notes,
            db=db,
        )
        await AuditService.log(
            event_type=AuditEventType.OCR_RERUN_REQUESTED,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            tenant_id=tenant_id,
            target_entity="ocr_review_queue",
            target_id=queue_id,
            metadata={"script_id": str(row.script_id)},
        )
        return OcrActionResponse(
            queue_id=row.id, script_id=row.script_id,
            review_status=row.review_status, action_taken=row.action_taken,
            completed_at=row.completed_at, message="OCR re-run requested.",
        )

    @staticmethod
    async def escalate(
        queue_id: UUID,
        reviewer_notes: str,
        current_user: CurrentUser,
        *,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> OcrActionResponse:
        await OcrReviewService._get_active(queue_id, db=db)
        row = await OcrQueueRepository.complete_review(
            queue_id=queue_id,
            new_status=OcrReviewStatus.ESCALATED,
            action_taken="ESCALATED",
            completed_by=current_user.id,
            reviewer_notes=reviewer_notes,
            db=db,
        )
        await AuditService.log(
            event_type=AuditEventType.OCR_ESCALATED,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            tenant_id=tenant_id,
            target_entity="ocr_review_queue",
            target_id=queue_id,
            metadata={"script_id": str(row.script_id), "reason": reviewer_notes},
        )
        return OcrActionResponse(
            queue_id=row.id, script_id=row.script_id,
            review_status=row.review_status, action_taken=row.action_taken,
            completed_at=row.completed_at, message="Script escalated to Admin.",
        )

    @staticmethod
    async def mark_unreadable(
        queue_id: UUID,
        reviewer_notes: str,
        current_user: CurrentUser,
        *,
        db: AsyncSession,
        tenant_id: UUID,
    ) -> OcrActionResponse:
        await OcrReviewService._get_active(queue_id, db=db)
        row = await OcrQueueRepository.complete_review(
            queue_id=queue_id,
            new_status=OcrReviewStatus.MARKED_UNREADABLE,
            action_taken="MARKED_UNREADABLE",
            completed_by=current_user.id,
            reviewer_notes=reviewer_notes,
            db=db,
        )
        await AuditService.log(
            event_type=AuditEventType.OCR_MARKED_UNREADABLE,
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            tenant_id=tenant_id,
            target_entity="ocr_review_queue",
            target_id=queue_id,
            metadata={"script_id": str(row.script_id), "reason": reviewer_notes},
        )
        return OcrActionResponse(
            queue_id=row.id, script_id=row.script_id,
            review_status=row.review_status, action_taken=row.action_taken,
            completed_at=row.completed_at, message="Script marked as unreadable.",
        )
