"""
M10 Bell Curve Normaliser — Service layer.

Architecture contract:
  - All business logic lives here; router is pure HTTP glue.
  - BellCurveServiceError carries code, message, status_code.
  - One human gate enforced here AND in the repository:
      Gate 1: ratify() → only way analysis reaches APPLIED/NO_ACTION
                        → only way bell_curve_normalized_scores gets rows
  - Celery task is dispatched by trigger(); task writes up to READY only.
  - bell_curve_decisions is written ONLY by ratify().
  - bell_curve_normalized_scores is written ONLY by ratify().
  - exam_score_ledger (M09) is NEVER modified by any method here.
  - preview() computes normalisation in-memory and returns without writing to DB.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m10_bell_curve.models import AnalysisStatus, BoardDecision, NormalisationMethod
from app.modules.m10_bell_curve.repository import (
    BellCurveAnalysisRepository,
    BellCurveDecisionRepository,
    BellCurveNormalisedScoreRepository,
    M09LedgerRepository,
    TaskJobPublicRepository,
)
from app.modules.m10_bell_curve.normalizer import apply_normalisation, preview_normalisation

logger = logging.getLogger("vidya.service.m10")


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------

class BellCurveServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# BellCurveService
# ---------------------------------------------------------------------------

class BellCurveService:

    # -----------------------------------------------------------------------
    # trigger — 409 guard + Celery dispatch
    # -----------------------------------------------------------------------

    @staticmethod
    async def trigger(
        exam_paper_id: UUID,
        triggered_by:  UUID,
        tenant_id:     UUID,
        schema_name:   str,
        db: AsyncSession,
    ):
        """
        Validate all scripts are finalised, create analysis record, dispatch Celery task.
        Returns (analysis, job_id).
        """
        # 409 guard: all scripts must be BOARD_FINALISED
        total, finalised = await M09LedgerRepository.count_scripts_for_paper(
            exam_paper_id, db=db
        )
        if total == 0:
            raise BellCurveServiceError(
                "NO_SCRIPTS",
                f"No scanned scripts found for exam paper {exam_paper_id}.",
                status_code=404,
            )
        if total != finalised:
            raise BellCurveServiceError(
                "SCORES_NOT_FINALISED",
                f"Only {finalised}/{total} scripts are BOARD_FINALISED. "
                "All scripts must be finalised before running bell curve analysis.",
                status_code=409,
            )

        # Create Celery job record in public schema (separate session — public schema)
        from app.database import async_session_public
        async with async_session_public() as pub_db:
            job = await TaskJobPublicRepository.create(
                task_name="app.workers.heavy.analyse_score_distribution",
                tenant_id=tenant_id,
                db=pub_db,
            )
        job_id = job.id

        analysis = await BellCurveAnalysisRepository.create(
            exam_paper_id   = exam_paper_id,
            triggered_by    = triggered_by,
            analysis_job_id = job_id,
            db              = db,
        )
        await db.commit()

        # Dispatch Celery task — import here to avoid circular deps
        from app.workers.heavy.analyse_score_distribution import analyse_score_distribution
        analyse_score_distribution.apply_async(
            kwargs={
                "job_id":       str(job_id),
                "analysis_id":  str(analysis.id),
                "schema_name":  schema_name,
            },
            _revert_table  = "bell_curve_analyses",
            _revert_pk     = str(analysis.id),
            _revert_schema = schema_name,
            _revert_status = AnalysisStatus.FAILED.value,
        )

        logger.info(
            "m10.trigger: analysis=%s paper=%s job=%s triggered_by=%s",
            analysis.id, exam_paper_id, job_id, triggered_by,
        )
        return analysis, job_id

    # -----------------------------------------------------------------------
    # get
    # -----------------------------------------------------------------------

    @staticmethod
    async def get(analysis_id: UUID, db: AsyncSession):
        obj = await BellCurveAnalysisRepository.get_by_id(analysis_id, db=db)
        if obj is None:
            raise BellCurveServiceError(
                "ANALYSIS_NOT_FOUND",
                f"Analysis {analysis_id} not found.",
                status_code=404,
            )
        return obj

    # -----------------------------------------------------------------------
    # list_all / list_for_paper
    # -----------------------------------------------------------------------

    @staticmethod
    async def list_all(offset: int, limit: int, db: AsyncSession):
        return await BellCurveAnalysisRepository.list_all(offset=offset, limit=limit, db=db)

    @staticmethod
    async def list_for_paper(exam_paper_id: UUID, offset: int, limit: int, db: AsyncSession):
        return await BellCurveAnalysisRepository.list_for_paper(
            exam_paper_id, offset=offset, limit=limit, db=db
        )

    # -----------------------------------------------------------------------
    # preview — no DB write
    # -----------------------------------------------------------------------

    @staticmethod
    async def preview(
        analysis_id: UUID,
        method:      str,
        params:      dict,
        db: AsyncSession,
    ) -> dict:
        """
        Compute projected normalisation without writing to DB.
        Returns PreviewNormalisationResponse-compatible dict.
        """
        analysis = await BellCurveService.get(analysis_id, db=db)
        if analysis.status not in (AnalysisStatus.READY, AnalysisStatus.BOARD_REVIEWED):
            raise BellCurveServiceError(
                "ANALYSIS_NOT_READY",
                f"Analysis {analysis_id} is {analysis.status.value}; "
                "preview requires status READY or BOARD_REVIEWED.",
                status_code=409,
            )

        ledger_rows = await M09LedgerRepository.get_scores_for_paper(
            analysis.exam_paper_id, db=db
        )
        if not ledger_rows:
            raise BellCurveServiceError(
                "NO_SCORES",
                "No finalised scores found for this exam paper.",
                status_code=404,
            )

        return preview_normalisation(ledger_rows, method, params)

    # -----------------------------------------------------------------------
    # ratify — Gate 1 (Board only)
    # -----------------------------------------------------------------------

    @staticmethod
    async def ratify(
        analysis_id:         UUID,
        decision:            str,
        normalisation_method: str,
        normalisation_params: dict,
        ratification_note:   str | None,
        ratified_by:         UUID,
        tenant_id:           UUID,
        schema_name:         str,
        db: AsyncSession,
    ):
        """
        GATE 1: Board ratifies.
        - Creates bell_curve_decisions (immutable after write).
        - If not REJECTED: writes bell_curve_normalized_scores (append-only).
        - Advances analysis status to APPLIED or NO_ACTION.
        - exam_score_ledger is NEVER modified.
        Returns (analysis, decision_obj, scores_written).
        """
        analysis = await BellCurveService.get(analysis_id, db=db)

        # Only READY or BOARD_REVIEWED analyses can be ratified
        if analysis.status not in (AnalysisStatus.READY, AnalysisStatus.BOARD_REVIEWED):
            raise BellCurveServiceError(
                "ANALYSIS_NOT_READY",
                f"Analysis {analysis_id} is {analysis.status.value}; "
                "ratification requires status READY or BOARD_REVIEWED.",
                status_code=409,
            )

        # Prevent double-ratification
        existing = await BellCurveDecisionRepository.get_for_analysis(analysis_id, db=db)
        if existing is not None:
            raise BellCurveServiceError(
                "ALREADY_RATIFIED",
                f"Analysis {analysis_id} has already been ratified.",
                status_code=409,
            )

        # Load raw scores from M09 (read-only)
        ledger_rows = await M09LedgerRepository.get_scores_for_paper(
            analysis.exam_paper_id, db=db
        )
        if not ledger_rows:
            raise BellCurveServiceError(
                "NO_SCORES",
                "No finalised scores found for this exam paper.",
                status_code=404,
            )

        # Compute projected stats
        preview = preview_normalisation(ledger_rows, normalisation_method, normalisation_params)
        projected_stats = preview["projected_stats"]

        # Write decision record (Gate 1 — immutable after this point)
        decision_obj = await BellCurveDecisionRepository.create(
            analysis_id          = analysis_id,
            exam_paper_id        = analysis.exam_paper_id,
            decision             = decision,
            normalisation_method = normalisation_method,
            normalisation_params = normalisation_params,
            projected_stats      = projected_stats,
            ratified_by          = ratified_by,
            ratification_note    = ratification_note,
            db                   = db,
        )

        scores_written = 0
        if decision != BoardDecision.REJECTED.value:
            # Compute and write normalised scores (append-only)
            normalised_rows = apply_normalisation(
                ledger_rows, normalisation_method, normalisation_params
            )
            await BellCurveNormalisedScoreRepository.bulk_create(
                normalised_rows,
                decision_id          = decision_obj.id,
                analysis_id          = analysis_id,
                exam_paper_id        = analysis.exam_paper_id,
                normalisation_method = normalisation_method,
                db                   = db,
            )
            scores_written = len(normalised_rows)
            await BellCurveAnalysisRepository.set_applied(analysis_id, db=db)
        else:
            await BellCurveAnalysisRepository.set_no_action(analysis_id, db=db)

        await db.commit()

        logger.info(
            "m10.ratify: analysis=%s decision=%s method=%s scores_written=%d ratified_by=%s",
            analysis_id, decision, normalisation_method, scores_written, ratified_by,
        )
        return analysis, decision_obj, scores_written

    # -----------------------------------------------------------------------
    # Ledger / decisions
    # -----------------------------------------------------------------------

    @staticmethod
    async def get_decision(decision_id: UUID, db: AsyncSession):
        obj = await BellCurveDecisionRepository.get_by_id(decision_id, db=db)
        if obj is None:
            raise BellCurveServiceError(
                "DECISION_NOT_FOUND",
                f"Decision {decision_id} not found.",
                status_code=404,
            )
        return obj

    @staticmethod
    async def list_decisions(offset: int, limit: int, db: AsyncSession):
        return await BellCurveDecisionRepository.list_all(offset=offset, limit=limit, db=db)

    @staticmethod
    async def list_ledger_for_paper(exam_paper_id: UUID, offset: int, limit: int, db: AsyncSession):
        return await BellCurveNormalisedScoreRepository.list_for_paper(
            exam_paper_id, offset=offset, limit=limit, db=db
        )

    @staticmethod
    async def grade_summary(exam_paper_id: UUID, db: AsyncSession) -> dict:
        """
        Compute grade distribution and pass/fail stats from normalised scores.
        Advisory only — never reads or writes raw M09 marks.
        """
        from app.modules.m10_bell_curve.grade_engine import grade_distribution

        items, total = await BellCurveNormalisedScoreRepository.list_for_paper(
            exam_paper_id, offset=0, limit=10_000, db=db
        )
        rows = [
            {"normalised_score": float(s.normalised_score), "max_marks": float(s.max_marks)}
            for s in items
        ]
        dist       = grade_distribution(rows)
        pass_count = sum(v for k, v in dist.items() if k != "F")
        fail_count = dist.get("F", 0)
        pass_rate  = round(pass_count / total * 100, 1) if total > 0 else 0.0

        return {
            "exam_paper_id": exam_paper_id,
            "total":         total,
            "pass_count":    pass_count,
            "fail_count":    fail_count,
            "pass_rate":     pass_rate,
            "grade_counts":  dist,
        }

