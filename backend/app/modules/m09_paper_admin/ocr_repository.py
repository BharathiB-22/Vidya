"""
M09.7 OCR Review Queue — data access layer.

All writes flow through explicit update methods; no repository method
ever applies a grade or changes a script's marks. ("AI advises, humans decide.")

Every query uses the tenant session (search_path already set) — no
cross-tenant access is possible.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m09_paper_admin.ocr_models import (
    OcrPriorityCategory,
    OcrReviewQueue,
    OcrReviewStatus,
    OcrThresholdConfig,
    OcrThresholdScope,
    PRIORITY_SCORE,
)


# ---------------------------------------------------------------------------
# Threshold repository
# ---------------------------------------------------------------------------

class OcrThresholdRepository:

    @staticmethod
    async def get_global(db: AsyncSession) -> OcrThresholdConfig | None:
        result = await db.execute(
            select(OcrThresholdConfig).where(
                OcrThresholdConfig.scope == OcrThresholdScope.GLOBAL,
                OcrThresholdConfig.scope_ref_id.is_(None),
                OcrThresholdConfig.is_active.is_(True),
            )
        )
        return result.scalars().first()

    @staticmethod
    async def get_exam_override(
        exam_paper_id: UUID,
        *,
        db: AsyncSession,
    ) -> OcrThresholdConfig | None:
        result = await db.execute(
            select(OcrThresholdConfig).where(
                OcrThresholdConfig.scope == OcrThresholdScope.EXAM,
                OcrThresholdConfig.scope_ref_id == exam_paper_id,
                OcrThresholdConfig.is_active.is_(True),
            )
        )
        return result.scalars().first()

    @staticmethod
    async def upsert(
        scope: str,
        scope_ref_id: UUID | None,
        low_threshold: float,
        medium_threshold: float,
        created_by: UUID,
        *,
        db: AsyncSession,
    ) -> OcrThresholdConfig:
        existing = await db.execute(
            select(OcrThresholdConfig).where(
                OcrThresholdConfig.scope == scope,
                OcrThresholdConfig.scope_ref_id == scope_ref_id
                if scope_ref_id else OcrThresholdConfig.scope_ref_id.is_(None),
            )
        )
        row = existing.scalars().first()
        if row:
            row.low_confidence_threshold    = low_threshold
            row.medium_confidence_threshold = medium_threshold
            row.is_active                   = True
            row.updated_at                  = datetime.now(timezone.utc)
        else:
            row = OcrThresholdConfig(
                id=uuid.uuid4(),
                scope=scope,
                scope_ref_id=scope_ref_id,
                low_confidence_threshold=low_threshold,
                medium_confidence_threshold=medium_threshold,
                is_active=True,
                created_by=created_by,
            )
            db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def list_all(db: AsyncSession) -> list[OcrThresholdConfig]:
        result = await db.execute(
            select(OcrThresholdConfig).order_by(
                OcrThresholdConfig.scope,
                OcrThresholdConfig.created_at,
            )
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Queue repository
# ---------------------------------------------------------------------------

class OcrQueueRepository:

    @staticmethod
    async def get_by_id(
        queue_id: UUID,
        *,
        db: AsyncSession,
    ) -> OcrReviewQueue | None:
        result = await db.execute(
            select(OcrReviewQueue).where(OcrReviewQueue.id == queue_id)
        )
        return result.scalars().first()

    @staticmethod
    async def get_by_script(
        script_id: UUID,
        *,
        db: AsyncSession,
    ) -> OcrReviewQueue | None:
        """Return the active (non-completed) queue entry for a script."""
        result = await db.execute(
            select(OcrReviewQueue).where(
                OcrReviewQueue.script_id == script_id,
                OcrReviewQueue.review_status.in_(
                    [OcrReviewStatus.PENDING, OcrReviewStatus.IN_REVIEW]
                ),
            )
        )
        return result.scalars().first()

    @staticmethod
    async def enqueue(
        script_id: UUID,
        exam_paper_id: UUID,
        priority_category: OcrPriorityCategory,
        original_ocr_text: str | None,
        ocr_confidence: float | None,
        *,
        db: AsyncSession,
    ) -> OcrReviewQueue:
        """Insert a new queue entry. Idempotent: skips if already queued."""
        existing = await OcrQueueRepository.get_by_script(script_id, db=db)
        if existing:
            return existing
        row = OcrReviewQueue(
            id=uuid.uuid4(),
            script_id=script_id,
            exam_paper_id=exam_paper_id,
            priority_category=priority_category,
            priority_score=PRIORITY_SCORE[priority_category],
            original_ocr_text=original_ocr_text,
            ocr_confidence=ocr_confidence,
            review_status=OcrReviewStatus.PENDING,
        )
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def list_queue(
        *,
        exam_paper_id: UUID | None = None,
        priority_category: str | None = None,
        review_status: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> tuple[list[OcrReviewQueue], int]:
        query = select(OcrReviewQueue)
        count_query = select(func.count()).select_from(OcrReviewQueue)

        if exam_paper_id:
            query = query.where(OcrReviewQueue.exam_paper_id == exam_paper_id)
            count_query = count_query.where(OcrReviewQueue.exam_paper_id == exam_paper_id)
        if priority_category:
            query = query.where(OcrReviewQueue.priority_category == priority_category)
            count_query = count_query.where(OcrReviewQueue.priority_category == priority_category)
        if review_status:
            query = query.where(OcrReviewQueue.review_status.in_(review_status))
            count_query = count_query.where(OcrReviewQueue.review_status.in_(review_status))

        total = (await db.execute(count_query)).scalar_one()
        rows  = (await db.execute(
            query.order_by(
                OcrReviewQueue.priority_score.desc(),
                OcrReviewQueue.created_at.asc(),
            ).offset(offset).limit(limit)
        )).scalars().all()
        return list(rows), total

    @staticmethod
    async def set_in_review(
        queue_id: UUID,
        reviewer_id: UUID,
        *,
        db: AsyncSession,
    ) -> OcrReviewQueue | None:
        row = await OcrQueueRepository.get_by_id(queue_id, db=db)
        if not row:
            return None
        row.review_status        = OcrReviewStatus.IN_REVIEW
        row.assigned_reviewer_id = reviewer_id
        row.review_started_at    = datetime.now(timezone.utc)
        row.updated_at           = datetime.now(timezone.utc)
        await db.flush()
        return row

    @staticmethod
    async def complete_review(
        queue_id: UUID,
        new_status: OcrReviewStatus,
        action_taken: str,
        completed_by: UUID,
        corrected_text: str | None = None,
        reviewer_notes: str | None = None,
        *,
        db: AsyncSession,
    ) -> OcrReviewQueue | None:
        row = await OcrQueueRepository.get_by_id(queue_id, db=db)
        if not row:
            return None
        row.review_status    = new_status
        row.action_taken     = action_taken
        row.completed_by     = completed_by
        row.completed_at     = datetime.now(timezone.utc)
        row.updated_at       = datetime.now(timezone.utc)
        if corrected_text is not None:
            row.corrected_text = corrected_text
        if reviewer_notes is not None:
            row.reviewer_notes = reviewer_notes
        await db.flush()
        return row

    # -----------------------------------------------------------------------
    # Dashboard counters
    # -----------------------------------------------------------------------

    @staticmethod
    async def dashboard_counts(
        *,
        exam_paper_id: UUID | None = None,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Aggregate counts for the dashboard. Uses raw SQL for efficiency."""
        paper_clause = "AND exam_paper_id = CAST(:pid AS uuid)" if exam_paper_id else ""
        params: dict = {}
        if exam_paper_id:
            params["pid"] = str(exam_paper_id)

        sql = f"""
            SELECT
                SUM(CASE WHEN review_status IN ('PENDING', 'IN_REVIEW') THEN 1 ELSE 0 END)
                    AS active_total,
                SUM(CASE WHEN review_status = 'PENDING'   THEN 1 ELSE 0 END) AS pending_total,
                SUM(CASE WHEN review_status = 'IN_REVIEW' THEN 1 ELSE 0 END) AS in_review_total,
                SUM(CASE WHEN priority_category = 'OCR_FAILURE'
                          AND review_status IN ('PENDING', 'IN_REVIEW') THEN 1 ELSE 0 END)
                    AS ocr_failure_count,
                SUM(CASE WHEN priority_category = 'LOW_CONFIDENCE'
                          AND review_status IN ('PENDING', 'IN_REVIEW') THEN 1 ELSE 0 END)
                    AS low_confidence_count,
                SUM(CASE WHEN priority_category = 'QUALITY_ISSUE'
                          AND review_status IN ('PENDING', 'IN_REVIEW') THEN 1 ELSE 0 END)
                    AS quality_issue_count,
                SUM(CASE WHEN priority_category = 'MEDIUM_CONFIDENCE'
                          AND review_status IN ('PENDING', 'IN_REVIEW') THEN 1 ELSE 0 END)
                    AS medium_confidence_count,
                SUM(CASE WHEN completed_at >= CURRENT_DATE THEN 1 ELSE 0 END)
                    AS completed_today
            FROM ocr_review_queue
            WHERE 1=1 {paper_clause}
        """
        row = (await db.execute(text(sql), params)).mappings().first()
        return dict(row) if row else {}

    # -----------------------------------------------------------------------
    # Analytics queries (called by analytics_repository extension)
    # -----------------------------------------------------------------------

    @staticmethod
    async def ocr_accuracy_stats(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> dict[str, Any]:
        paper_clause = "AND exam_paper_id = CAST(:pid AS uuid)" if exam_paper_id else ""
        params: dict = {}
        if exam_paper_id:
            params["pid"] = str(exam_paper_id)

        sql = f"""
            SELECT
                COUNT(*)                                              AS total_queued,
                SUM(CASE WHEN action_taken = 'CORRECTED' THEN 1 ELSE 0 END)
                                                                      AS total_corrected,
                SUM(CASE WHEN action_taken = 'ACCEPTED'  THEN 1 ELSE 0 END)
                                                                      AS total_accepted,
                SUM(CASE WHEN action_taken = 'RERUN_REQUESTED' THEN 1 ELSE 0 END)
                                                                      AS total_rerun,
                SUM(CASE WHEN action_taken = 'MARKED_UNREADABLE' THEN 1 ELSE 0 END)
                                                                      AS total_unreadable,
                AVG(ocr_confidence)                                   AS avg_confidence,
                COUNT(DISTINCT assigned_reviewer_id)                  AS reviewer_count
            FROM ocr_review_queue
            WHERE 1=1 {paper_clause}
        """
        row = (await db.execute(text(sql), params)).mappings().first()
        return dict(row) if row else {}

    @staticmethod
    async def ocr_corrections_per_reviewer(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        paper_clause = "AND exam_paper_id = CAST(:pid AS uuid)" if exam_paper_id else ""
        params: dict = {}
        if exam_paper_id:
            params["pid"] = str(exam_paper_id)
        sql = f"""
            SELECT
                assigned_reviewer_id::text  AS reviewer_id,
                COUNT(*)                    AS total_reviewed,
                SUM(CASE WHEN action_taken = 'CORRECTED' THEN 1 ELSE 0 END) AS corrections
            FROM ocr_review_queue
            WHERE assigned_reviewer_id IS NOT NULL {paper_clause}
            GROUP BY assigned_reviewer_id
            ORDER BY corrections DESC
        """
        rows = (await db.execute(text(sql), params)).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    async def ocr_quality_distribution(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        paper_clause = "AND exam_paper_id = CAST(:pid AS uuid)" if exam_paper_id else ""
        params: dict = {}
        if exam_paper_id:
            params["pid"] = str(exam_paper_id)
        sql = f"""
            SELECT
                priority_category          AS category,
                COUNT(*)                   AS count
            FROM ocr_review_queue
            WHERE 1=1 {paper_clause}
            GROUP BY priority_category
            ORDER BY priority_category
        """
        rows = (await db.execute(text(sql), params)).mappings().all()
        return [dict(r) for r in rows]

    # -----------------------------------------------------------------------
    # Compliance report queries
    # -----------------------------------------------------------------------

    @staticmethod
    async def ocr_correction_history(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        paper_clause = "AND q.exam_paper_id = CAST(:pid AS uuid)" if exam_paper_id else ""
        params: dict = {}
        if exam_paper_id:
            params["pid"] = str(exam_paper_id)
        sql = f"""
            SELECT
                q.id::text                   AS queue_id,
                q.script_id::text            AS script_id,
                ss.masked_id,
                q.exam_paper_id::text        AS exam_paper_id,
                q.priority_category,
                q.ocr_confidence,
                q.action_taken,
                q.assigned_reviewer_id::text AS reviewer_id,
                q.reviewer_notes,
                q.review_started_at,
                q.completed_at
            FROM ocr_review_queue q
            LEFT JOIN scanned_scripts ss ON ss.id = q.script_id
            WHERE q.action_taken = 'CORRECTED' {paper_clause}
            ORDER BY q.completed_at DESC
        """
        rows = (await db.execute(text(sql), params)).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    async def ocr_reviewer_activity(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        paper_clause = "AND exam_paper_id = CAST(:pid AS uuid)" if exam_paper_id else ""
        params: dict = {}
        if exam_paper_id:
            params["pid"] = str(exam_paper_id)
        sql = f"""
            SELECT
                assigned_reviewer_id::text  AS reviewer_id,
                COUNT(*)                    AS total_reviewed,
                SUM(CASE WHEN action_taken = 'CORRECTED'         THEN 1 ELSE 0 END) AS corrections,
                SUM(CASE WHEN action_taken = 'ACCEPTED'          THEN 1 ELSE 0 END) AS accepted,
                SUM(CASE WHEN action_taken = 'RERUN_REQUESTED'   THEN 1 ELSE 0 END) AS rerun_requested,
                SUM(CASE WHEN action_taken = 'ESCALATED'         THEN 1 ELSE 0 END) AS escalated,
                SUM(CASE WHEN action_taken = 'MARKED_UNREADABLE' THEN 1 ELSE 0 END) AS marked_unreadable,
                MAX(completed_at)           AS last_activity_at
            FROM ocr_review_queue
            WHERE assigned_reviewer_id IS NOT NULL {paper_clause}
            GROUP BY assigned_reviewer_id
            ORDER BY last_activity_at DESC NULLS LAST
        """
        rows = (await db.execute(text(sql), params)).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    async def ocr_escalation_report(
        exam_paper_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        paper_clause = "AND q.exam_paper_id = CAST(:pid AS uuid)" if exam_paper_id else ""
        params: dict = {}
        if exam_paper_id:
            params["pid"] = str(exam_paper_id)
        sql = f"""
            SELECT
                q.id::text                   AS queue_id,
                q.script_id::text            AS script_id,
                ss.masked_id,
                q.exam_paper_id::text        AS exam_paper_id,
                q.priority_category,
                q.ocr_confidence,
                q.assigned_reviewer_id::text AS reviewer_id,
                q.reviewer_notes,
                q.review_started_at,
                q.completed_at
            FROM ocr_review_queue q
            LEFT JOIN scanned_scripts ss ON ss.id = q.script_id
            WHERE q.action_taken = 'ESCALATED' {paper_clause}
            ORDER BY q.completed_at DESC
        """
        rows = (await db.execute(text(sql), params)).mappings().all()
        return [dict(r) for r in rows]
