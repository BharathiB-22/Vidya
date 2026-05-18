"""
M10 Bell Curve Normaliser — Repository layer.

ORM CRUD for bell_curve_analyses, bell_curve_decisions, bell_curve_normalized_scores.
Read-only access to M09 exam_score_ledger and script_evaluations.

Append-only invariant: no UPDATE or DELETE methods on BellCurveNormalisedScore.
Human-gate invariant: no method here sets analysis.status to APPLIED/NO_ACTION —
  that is enforced exclusively in service.py.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m10_bell_curve.models import (
    AnalysisStatus,
    BellCurveAnalysis,
    BellCurveDecision,
    BellCurveNormalisedScore,
)


# ---------------------------------------------------------------------------
# BellCurveAnalysisRepository
# ---------------------------------------------------------------------------

class BellCurveAnalysisRepository:

    @staticmethod
    async def create(
        *,
        exam_paper_id:   UUID,
        triggered_by:    UUID,
        analysis_job_id: UUID,
        db: AsyncSession,
    ) -> BellCurveAnalysis:
        from datetime import datetime, timezone
        obj = BellCurveAnalysis(
            exam_paper_id   = exam_paper_id,
            triggered_by    = triggered_by,
            analysis_job_id = analysis_job_id,
            status          = AnalysisStatus.PENDING,
            triggered_at    = datetime.now(timezone.utc),
        )
        db.add(obj)
        await db.flush()
        return obj

    @staticmethod
    async def get_by_id(
        analysis_id: UUID,
        db: AsyncSession,
    ) -> BellCurveAnalysis | None:
        stmt = select(BellCurveAnalysis).where(BellCurveAnalysis.id == analysis_id)
        return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def list_all(
        *,
        offset: int = 0,
        limit:  int = 20,
        db: AsyncSession,
    ) -> tuple[list[BellCurveAnalysis], int]:
        count_stmt = select(func.count()).select_from(BellCurveAnalysis)
        total      = (await db.execute(count_stmt)).scalar_one()
        stmt = (
            select(BellCurveAnalysis)
            .order_by(BellCurveAnalysis.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = list((await db.execute(stmt)).scalars().all())
        return items, total

    @staticmethod
    async def list_for_paper(
        exam_paper_id: UUID,
        *,
        offset: int = 0,
        limit:  int = 20,
        db: AsyncSession,
    ) -> tuple[list[BellCurveAnalysis], int]:
        base = select(BellCurveAnalysis).where(
            BellCurveAnalysis.exam_paper_id == exam_paper_id
        )
        total = (await db.execute(
            select(func.count()).select_from(base.subquery())
        )).scalar_one()
        items = list((await db.execute(
            base.order_by(BellCurveAnalysis.created_at.desc()).offset(offset).limit(limit)
        )).scalars().all())
        return items, total

    @staticmethod
    async def set_analysing(analysis_id: UUID, db: AsyncSession) -> None:
        obj = await BellCurveAnalysisRepository.get_by_id(analysis_id, db=db)
        if obj:
            obj.status = AnalysisStatus.ANALYSING
            await db.flush()

    @staticmethod
    async def set_ready(
        analysis_id: UUID,
        *,
        score_count:              int,
        raw_stats:                dict,
        anomalies:                list,
        normalisation_suggestion: dict,
        cross_evaluator_stats:    list,
        db: AsyncSession,
    ) -> BellCurveAnalysis | None:
        from datetime import datetime, timezone
        obj = await BellCurveAnalysisRepository.get_by_id(analysis_id, db=db)
        if obj:
            obj.score_count              = score_count
            obj.raw_stats                = raw_stats
            obj.anomalies                = anomalies
            obj.normalisation_suggestion = normalisation_suggestion
            obj.cross_evaluator_stats    = cross_evaluator_stats
            obj.status                   = AnalysisStatus.READY
            obj.analysis_completed_at    = datetime.now(timezone.utc)
            await db.flush()
        return obj

    @staticmethod
    async def set_failed(analysis_id: UUID, db: AsyncSession) -> None:
        obj = await BellCurveAnalysisRepository.get_by_id(analysis_id, db=db)
        if obj:
            obj.status = AnalysisStatus.FAILED
            await db.flush()

    @staticmethod
    async def set_applied(analysis_id: UUID, db: AsyncSession) -> None:
        """Called only by service.ratify — never by Celery."""
        obj = await BellCurveAnalysisRepository.get_by_id(analysis_id, db=db)
        if obj:
            obj.status = AnalysisStatus.APPLIED
            await db.flush()

    @staticmethod
    async def set_no_action(analysis_id: UUID, db: AsyncSession) -> None:
        """Called only by service.ratify (REJECTED decision) — never by Celery."""
        obj = await BellCurveAnalysisRepository.get_by_id(analysis_id, db=db)
        if obj:
            obj.status = AnalysisStatus.NO_ACTION
            await db.flush()


# ---------------------------------------------------------------------------
# BellCurveDecisionRepository
# ---------------------------------------------------------------------------

class BellCurveDecisionRepository:

    @staticmethod
    async def create(
        *,
        analysis_id:          UUID,
        exam_paper_id:        UUID,
        decision:             str,
        normalisation_method: str,
        normalisation_params: dict,
        projected_stats:      dict | None,
        ratified_by:          UUID,
        ratification_note:    str | None,
        db: AsyncSession,
    ) -> BellCurveDecision:
        obj = BellCurveDecision(
            analysis_id          = analysis_id,
            exam_paper_id        = exam_paper_id,
            decision             = decision,
            normalisation_method = normalisation_method,
            normalisation_params = normalisation_params,
            projected_stats      = projected_stats,
            ratified_by          = ratified_by,
            ratification_note    = ratification_note,
        )
        db.add(obj)
        await db.flush()
        return obj

    @staticmethod
    async def get_by_id(
        decision_id: UUID,
        db: AsyncSession,
    ) -> BellCurveDecision | None:
        stmt = select(BellCurveDecision).where(BellCurveDecision.id == decision_id)
        return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def get_for_analysis(
        analysis_id: UUID,
        db: AsyncSession,
    ) -> BellCurveDecision | None:
        stmt = select(BellCurveDecision).where(
            BellCurveDecision.analysis_id == analysis_id
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def list_all(
        *,
        offset: int = 0,
        limit:  int = 20,
        db: AsyncSession,
    ) -> tuple[list[BellCurveDecision], int]:
        total = (await db.execute(
            select(func.count()).select_from(BellCurveDecision)
        )).scalar_one()
        items = list((await db.execute(
            select(BellCurveDecision)
            .order_by(BellCurveDecision.ratified_at.desc())
            .offset(offset).limit(limit)
        )).scalars().all())
        return items, total


# ---------------------------------------------------------------------------
# BellCurveNormalisedScoreRepository — append-only; no update/delete methods
# ---------------------------------------------------------------------------

class BellCurveNormalisedScoreRepository:

    @staticmethod
    async def bulk_create(
        rows: list[dict],
        *,
        decision_id:          UUID,
        analysis_id:          UUID,
        exam_paper_id:        UUID,
        normalisation_method: str,
        db: AsyncSession,
    ) -> list[BellCurveNormalisedScore]:
        """
        Insert one row per student.  Append-only — no UPDATE or DELETE ever.
        rows: [{student_user_id, student_roll_ref, raw_score, normalised_score, max_marks}]
        """
        objs = [
            BellCurveNormalisedScore(
                decision_id          = decision_id,
                analysis_id          = analysis_id,
                exam_paper_id        = exam_paper_id,
                student_user_id      = row.get("student_user_id"),
                student_roll_ref     = row.get("student_roll_ref"),
                raw_score            = row["raw_score"],
                normalised_score     = row["normalised_score"],
                max_marks            = row["max_marks"],
                normalisation_method = normalisation_method,
            )
            for row in rows
        ]
        db.add_all(objs)
        await db.flush()
        return objs

    @staticmethod
    async def list_for_paper(
        exam_paper_id: UUID,
        *,
        offset: int = 0,
        limit:  int = 50,
        db: AsyncSession,
    ) -> tuple[list[BellCurveNormalisedScore], int]:
        base = select(BellCurveNormalisedScore).where(
            BellCurveNormalisedScore.exam_paper_id == exam_paper_id
        )
        total = (await db.execute(
            select(func.count()).select_from(base.subquery())
        )).scalar_one()
        items = list((await db.execute(
            base.order_by(BellCurveNormalisedScore.created_at.asc())
            .offset(offset).limit(limit)
        )).scalars().all())
        return items, total


# ---------------------------------------------------------------------------
# TaskJobPublicRepository — mirrors M08/M09 pattern exactly
# ---------------------------------------------------------------------------

class TaskJobPublicRepository:
    """
    Operates on public.task_jobs. Caller must pass a session from
    async_session_public() (not the tenant session).
    """

    @staticmethod
    async def create(
        *,
        task_name: str,
        tenant_id: UUID,
        db: AsyncSession,
    ):
        import uuid as _uuid
        from sqlalchemy import text as sa_text
        result = await db.execute(
            sa_text(
                "INSERT INTO public.task_jobs (id, task_name, tenant_id, status, created_at) "
                "VALUES (:id, :task_name, :tenant_id, 'PENDING', now()) RETURNING *"
            ),
            {
                "id":        str(_uuid.uuid4()),
                "task_name": task_name,
                "tenant_id": str(tenant_id),
            },
        )
        row = result.mappings().one()

        class _Job:
            pass

        job = _Job()
        job.id = UUID(row["id"]) if isinstance(row["id"], str) else row["id"]
        return job

    @staticmethod
    async def get_by_id(job_id: UUID, tenant_id: UUID, db: AsyncSession) -> dict | None:
        from sqlalchemy import text as sa_text
        result = await db.execute(
            sa_text(
                "SELECT id, status, result, error, created_at, started_at, completed_at "
                "FROM public.task_jobs WHERE id = CAST(:id AS uuid) AND tenant_id = CAST(:tenant_id AS uuid)"
            ),
            {"id": str(job_id), "tenant_id": str(tenant_id)},
        )
        row = result.mappings().one_or_none()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# M09LedgerRepository — read-only access to M09 exam_score_ledger
# ---------------------------------------------------------------------------

class M09LedgerRepository:
    """
    Read-only access to M09 tables.  M10 never writes to exam_score_ledger.
    """

    @staticmethod
    async def get_scores_for_paper(
        exam_paper_id: UUID,
        db: AsyncSession,
    ) -> list[dict]:
        """
        Return all finalised scores for an exam paper.
        [{student_user_id, student_roll_ref, total_marks, max_marks, finalised_by}]
        """
        stmt = text("""
            SELECT student_user_id, student_roll_ref, total_marks, max_marks, finalised_by
            FROM exam_score_ledger
            WHERE exam_paper_id = :paper_id
            ORDER BY created_at ASC
        """)
        rows = (await db.execute(stmt, {"paper_id": str(exam_paper_id)})).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    async def count_scripts_for_paper(
        exam_paper_id: UUID,
        db: AsyncSession,
    ) -> tuple[int, int]:
        """
        Returns (total_scripts, finalised_count) for an exam paper.
        Used to enforce the 409 guard before triggering analysis.
        """
        stmt = text("""
            SELECT
                COUNT(*)                                        AS total,
                COUNT(*) FILTER (WHERE status = 'BOARD_FINALISED') AS finalised
            FROM scanned_scripts
            WHERE exam_paper_id = :paper_id
        """)
        row = (await db.execute(stmt, {"paper_id": str(exam_paper_id)})).mappings().one()
        return int(row["total"]), int(row["finalised"])

    @staticmethod
    async def get_evaluator_stats_for_paper(
        exam_paper_id: UUID,
        db: AsyncSession,
    ) -> list[dict]:
        """
        Per-evaluator mean/std/count for cross-faculty bias detection.
        [{evaluator_id, mean, std, count}]
        """
        stmt = text("""
            SELECT
                ss.evaluator_id,
                AVG(se.evaluator_marks)    AS mean,
                STDDEV(se.evaluator_marks) AS std,
                COUNT(se.id)               AS count
            FROM script_evaluations se
            JOIN scanned_scripts ss ON ss.id = se.script_id
            WHERE ss.exam_paper_id = :paper_id
              AND se.evaluation_round = 'PRIMARY'
              AND se.evaluator_marks IS NOT NULL
              AND ss.evaluator_id IS NOT NULL
            GROUP BY ss.evaluator_id
        """)
        rows = (await db.execute(stmt, {"paper_id": str(exam_paper_id)})).mappings().all()
        return [dict(r) for r in rows]
