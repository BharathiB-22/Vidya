"""
Celery heavy-queue task: analyse score distribution for an exam paper (M10).

Flow:
  1. Load BellCurveAnalysis from DB (expected status: PENDING or ANALYSING).
  2. Set status → ANALYSING.
  3. Load exam_score_ledger rows for exam_paper_id (read-only; M09 table).
  4. Load cross-evaluator stats from script_evaluations (M09 table).
  5. Compute stats: mean, std, median, skewness, kurtosis, Q1/Q3, histogram.
  6. Detect anomalies: zero inflation, ceiling effect, bimodality (BC), skew.
  7. Compute cross-evaluator z-scores.
  8. Generate normalisation suggestion.
  9. Set analysis status → READY; write all stats fields.
  10. Send Board notification.
  11. Audit BELL_CURVE_ANALYSIS_COMPLETED.

On unrecoverable failure:
  - Set status → FAILED.
  - Audit BELL_CURVE_ANALYSIS_FAILED.
  - Re-raise so Celery marks the task FAILED.

Human-gate invariants:
  - This task NEVER sets status beyond READY.
  - bell_curve_decisions is NEVER written by this task.
  - bell_curve_normalized_scores is NEVER written by this task.
  - exam_score_ledger (M09) is NEVER modified by this task.
"""
import asyncio
import logging
import sys

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m10.analyse_score_distribution")

_async_engine = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.config import settings
        _async_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return _async_engine


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.analyse_score_distribution",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=2,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def analyse_score_distribution(
    *,
    job_id: str,
    analysis_id: str,
    schema_name: str,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_analysis(
            analysis_id=analysis_id,
            schema_name=schema_name,
        )
    )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_analysis(*, analysis_id: str, schema_name: str) -> dict:
    from uuid import UUID
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m10_bell_curve.models import AnalysisStatus
    from app.modules.m10_bell_curve.repository import (
        BellCurveAnalysisRepository,
        M09LedgerRepository,
    )
    from app.modules.m10_bell_curve.stats_engine import (
        compute_stats,
        cross_evaluator_stats,
        detect_anomalies,
        suggest_normalisation,
    )

    engine       = _get_async_engine()
    analysis_uuid = UUID(analysis_id)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(text(f"SET search_path TO {schema_name}, public"))

        # 1. Load analysis record
        analysis = await BellCurveAnalysisRepository.get_by_id(analysis_uuid, db=session)
        if analysis is None:
            raise ValueError(
                f"BellCurveAnalysis {analysis_id} not found in schema {schema_name!r}."
            )

        exam_paper_id = analysis.exam_paper_id

        try:
            # 2. Mark as ANALYSING
            await BellCurveAnalysisRepository.set_analysing(analysis_uuid, db=session)
            await session.commit()

            # 3. Load finalised scores from M09 exam_score_ledger (read-only)
            ledger_rows = await M09LedgerRepository.get_scores_for_paper(
                exam_paper_id, db=session
            )
            if not ledger_rows:
                raise ValueError(
                    f"No finalised scores found for exam_paper={exam_paper_id}."
                )

            scores    = [float(r["total_marks"]) for r in ledger_rows]
            max_marks = float(ledger_rows[0]["max_marks"])

            # 4. Load cross-evaluator data from M09 script_evaluations (read-only)
            evaluator_rows = await M09LedgerRepository.get_evaluator_stats_for_paper(
                exam_paper_id, db=session
            )

            # 5. Compute descriptive statistics
            raw_stats = compute_stats(scores, max_marks)

            # 6. Detect anomalies
            anomalies = detect_anomalies(scores, max_marks, raw_stats)

            # 7. Cross-evaluator z-scores
            ce_stats = cross_evaluator_stats(evaluator_rows)

            # 8. Generate normalisation suggestion
            suggestion = suggest_normalisation(scores, max_marks, raw_stats, anomalies)

            # 9. Write results and advance to READY
            await BellCurveAnalysisRepository.set_ready(
                analysis_uuid,
                score_count              = len(scores),
                raw_stats                = raw_stats,
                anomalies                = anomalies,
                normalisation_suggestion = suggestion,
                cross_evaluator_stats    = ce_stats,
                db                       = session,
            )
            await session.commit()

            # 10. Audit success
            await AuditService.log(
                AuditEventType.BELL_CURVE_ANALYSIS_COMPLETED,
                actor_user_id=None,
                actor_role="SYSTEM",
                tenant_id=None,
                schema_name=schema_name,
                target_entity="bell_curve_analysis",
                target_id=analysis_id,
                metadata={
                    "score_count":    len(scores),
                    "anomaly_count":  len(anomalies),
                    "suggestion":     suggestion.get("method"),
                    "ce_outliers":    sum(1 for e in ce_stats if e.get("is_outlier")),
                },
            )

            logger.info(
                "m10.analyse: analysis=%s paper=%s scores=%d anomalies=%d",
                analysis_id, exam_paper_id, len(scores), len(anomalies),
            )

            return {
                "analysis_id":   analysis_id,
                "status":        AnalysisStatus.READY.value,
                "score_count":   len(scores),
                "anomaly_count": len(anomalies),
            }

        except Exception as exc:
            logger.error(
                "m10.analyse: failed analysis=%s: %s", analysis_id, exc, exc_info=True
            )
            try:
                await BellCurveAnalysisRepository.set_failed(analysis_uuid, db=session)
                await session.commit()
            except Exception:
                pass
            try:
                await AuditService.log(
                    AuditEventType.BELL_CURVE_ANALYSIS_FAILED,
                    actor_user_id=None,
                    actor_role="SYSTEM",
                    tenant_id=None,
                    schema_name=schema_name,
                    target_entity="bell_curve_analysis",
                    target_id=analysis_id,
                    metadata={"error": str(exc)[:500]},
                )
            except Exception:
                pass
            raise
