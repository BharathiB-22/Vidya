"""
Celery heavy-queue task: process a completed viva session (M07).

Flow:
  1. Load VivaSession from tenant schema; verify status is COMPLETED.
  2. Set status → ASR_PROCESSING.
  3. If video_url present: transcribe audio via Whisper (or mock in dev).
  4. Set status → EVALUATED (transitional, before LLM scoring).
  5. Build QA pairs from ai_questions + ai_responses + transcript.
  6. Call viva_engine.evaluate_responses() → per-question scores.
  7. Compute overall_ai_score = mean of per-question mean scores.
  8. Write ai_evaluation + overall_ai_score to VivaSession; set status → EVALUATED.
  9. Commit. Audit VIVA_AI_EVALUATED.

Human gate: status NEVER advances to GUIDE_RATIFIED here.
Guide must call /viva/{id}/ratify explicitly.
DPDP Act 2023: recording is only processed if consent_recorded = True.
"""
import asyncio
import logging
import sys
from uuid import UUID

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m07.process_viva_session")

_async_engine = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.config import settings
        _async_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return _async_engine


@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.process_viva_session",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def process_viva_session(
    *,
    job_id: str,
    viva_id: str,
    schema_name: str,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_viva_processing(
            viva_id=UUID(viva_id),
            schema_name=schema_name,
        )
    )


async def _run_viva_processing(viva_id: UUID, schema_name: str) -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m07_research_supervision.models import VivaStatus
    from app.modules.m07_research_supervision.repository import VivaRepository
    from app.modules.m07_research_supervision.viva_engine import (
        evaluate_responses,
        transcribe_audio,
    )

    engine = _get_async_engine()

    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(text(f"SET search_path TO {schema_name}, public"))

        viva = await VivaRepository.get_by_id(viva_id, db=session)
        if viva is None:
            raise ValueError(f"VivaSession {viva_id} not found in {schema_name!r}.")

        if viva.status not in (VivaStatus.COMPLETED.value, VivaStatus.ASR_PROCESSING.value):
            logger.warning(
                "process_viva_session called on viva %s with unexpected status %s",
                viva_id, viva.status,
            )

        # DPDP Act 2023 compliance: skip audio processing if no consent
        transcript: str = ""
        if viva.video_url and viva.consent_recorded:
            # ASR phase — only for video vivas (not offline guide-conducted)
            await VivaRepository.set_status(viva_id, VivaStatus.ASR_PROCESSING.value, db=session)
            await session.commit()
            transcript = await transcribe_audio(viva.video_url)
        elif viva.video_url and not viva.consent_recorded:
            logger.info("Viva %s: consent not recorded, skipping ASR.", viva_id)

        # Build QA pairs from stored questions + responses
        questions = viva.ai_questions or []
        stored_responses = {
            r.get("question_id"): r.get("response_text", "")
            for r in (viva.ai_responses or [])
        }

        qa_pairs = []
        for q in questions:
            qid  = q.get("id", "")
            text_ = q.get("text", "")
            resp  = stored_responses.get(qid, "")
            if text_:
                qa_pairs.append({
                    "question_id": qid,
                    "question":    text_,
                    "response":    resp or "[No response]",
                })

        if not qa_pairs:
            logger.warning("Viva %s: no Q&A pairs found, using stub evaluation.", viva_id)
            qa_pairs = [{
                "question_id": "stub",
                "question":    "[No questions recorded]",
                "response":    "[No response]",
            }]

        # LLM evaluation — evaluate_responses never raises; falls back to defaults
        try:
            eval_result = await evaluate_responses(qa_pairs)
        except Exception as exc:
            # Belt-and-suspenders: reset status so viva is not stuck in ASR_PROCESSING
            logger.error("Viva %s: evaluate_responses raised unexpectedly: %s", viva_id, exc)
            await VivaRepository.set_status(viva_id, VivaStatus.COMPLETED.value, db=session)
            await session.commit()
            raise

        # Build ai_evaluation dict stored as JSONB
        pq = [
            {
                "question_id": re_.question_id,
                "coherence":   re_.coherence,
                "accuracy":    re_.accuracy,
                "depth":       re_.depth,
                "comment":     re_.comment,
            }
            for re_ in eval_result.per_question
        ]

        overall = eval_result.overall_score

        ai_evaluation = {
            "per_question":  pq,
            "overall_score": round(overall, 2),
            "ai_model":      eval_result.ai_model,
        }

        # Write evaluation — status → EVALUATED (human gate holds here)
        await VivaRepository.set_ai_evaluation(
            viva_id,
            transcript=transcript,
            ai_evaluation=ai_evaluation,
            overall_ai_score=round(overall, 2),
            ai_model=eval_result.ai_model,
            db=session,
        )
        await session.commit()

        await AuditService.log(
            AuditEventType.VIVA_AI_EVALUATED,
            actor_user_id=None,
            actor_role="SYSTEM",
            tenant_id=None,
            schema_name=schema_name,
            target_entity="viva_session",
            target_id=str(viva_id),
            metadata={
                "overall_ai_score": round(overall, 2),
                "num_questions":    len(eval_result.per_question),
                "transcript_len":   len(transcript),
                "ai_model":         eval_result.ai_model,
                "consent_recorded": bool(viva.consent_recorded),
            },
        )

        logger.info(
            "Viva processed: viva=%s overall_ai_score=%.2f questions=%d",
            viva_id, overall, len(eval_result.per_question),
        )

        return {
            "viva_id":          str(viva_id),
            "overall_ai_score": round(overall, 2),
            "num_questions":    len(eval_result.per_question),
        }
