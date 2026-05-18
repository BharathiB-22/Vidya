"""
Celery heavy-queue task: score a scanned answer script (M09).

Flow:
  1. Load ScannedScript from DB (expected status: PROCESSING).
  2. Load ExamQuestions for exam_paper_id from M08 exam_questions table (same schema).
  3. Call script_scorer.score_script(questions, ocr_text).
  4. Bulk-create ScriptEvaluation rows with AI-suggested marks.
  5a. If OCR unavailable (had_ocr=False): set script status → REVIEW_REQUIRED.
  5b. Else:                               set script status → SCORED + objective_auto_score.
  6. Commit.  Audit SCRIPT_SCORING_COMPLETED.

On unrecoverable failure:
  - Set status → FAILED.
  - Audit SCRIPT_SCORING_FAILED.
  - Re-raise so Celery marks the task FAILED.

Human-gate invariants:
  - This task NEVER sets status beyond SCORED.
  - evaluator_marks is NEVER written by this task.
  - exam_score_ledger is NEVER written by this task.
  - student_user_id is NEVER logged or exposed by this task.
"""
import asyncio
import logging
import sys

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m09.score_scanned_script")

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
    name="app.workers.heavy.score_scanned_script",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=2,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def score_scanned_script(
    *,
    job_id: str,
    script_id: str,
    schema_name: str,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_scoring(
            script_id=script_id,
            schema_name=schema_name,
        )
    )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_scoring(*, script_id: str, schema_name: str) -> dict:
    from uuid import UUID
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m08_exam_setter.repository import ExamQuestionRepository
    from app.modules.m09_paper_admin.models import ScriptStatus
    from app.modules.m09_paper_admin.repository import (
        ScriptEvaluationRepository,
        ScriptRepository,
    )
    from app.modules.m09_paper_admin.script_scorer import score_script

    engine = _get_async_engine()
    script_uuid = UUID(script_id)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(text(f"SET search_path TO {schema_name}, public"))

        # 1. Load script
        script = await ScriptRepository.get_by_id(script_uuid, db=session)
        if script is None:
            raise ValueError(
                f"ScannedScript {script_id} not found in schema {schema_name!r}."
            )

        exam_paper_id = script.exam_paper_id
        ocr_text = script.ocr_text  # None in this sprint; OCR pipeline is future work

        try:
            # 2. Load exam questions from M08 table (same tenant schema)
            questions = await ExamQuestionRepository.list_by_paper(
                exam_paper_id, db=session
            )

            if not questions:
                logger.warning(
                    "No questions found for exam_paper=%s (script=%s) — REVIEW_REQUIRED.",
                    exam_paper_id, script_id,
                )
                await ScriptRepository.set_review_required(script_uuid, db=session)
                await session.commit()
                await AuditService.log(
                    AuditEventType.SCRIPT_SCORING_FAILED,
                    actor_user_id=None,
                    actor_role="SYSTEM",
                    tenant_id=None,
                    schema_name=schema_name,
                    target_entity="scanned_script",
                    target_id=script_id,
                    metadata={"reason": "No exam questions found for paper."},
                )
                return {
                    "script_id": script_id,
                    "status": ScriptStatus.REVIEW_REQUIRED.value,
                    "reason": "no_questions",
                }

            # 3. Score the script (AI + auto MCQ)
            result = await score_script(questions, ocr_text)

            # 4. Bulk-create ScriptEvaluation rows with AI suggestions
            suggestions = [
                {
                    "question_id":        qs.question_id,
                    "question_type":      qs.question_type,
                    "max_marks":          qs.max_marks,
                    "ai_suggested_marks": qs.ai_suggested_marks,
                    "ai_justification":   qs.ai_justification,
                    "ai_model":           qs.ai_model,
                    "prompt_hash":        qs.prompt_hash,
                }
                for qs in result.scores
            ]
            await ScriptEvaluationRepository.bulk_create_ai_suggestions(
                suggestions, script_id=script_uuid, db=session
            )

            # 5. Advance script status — never beyond SCORED
            if not result.had_ocr:
                # OCR not available; evaluator must enter marks manually
                await ScriptRepository.set_review_required(script_uuid, db=session)
                new_status = ScriptStatus.REVIEW_REQUIRED.value
            else:
                await ScriptRepository.set_scored(
                    script_uuid,
                    objective_auto_score=result.objective_auto_score,
                    db=session,
                )
                new_status = ScriptStatus.SCORED.value

            await session.commit()

            # 6. Audit
            await AuditService.log(
                AuditEventType.SCRIPT_SCORING_COMPLETED,
                actor_user_id=None,
                actor_role="SYSTEM",
                tenant_id=None,
                schema_name=schema_name,
                target_entity="scanned_script",
                target_id=script_id,
                metadata={
                    "question_count":       len(result.scores),
                    "objective_auto_score": result.objective_auto_score,
                    "had_ocr":              result.had_ocr,
                    "final_status":         new_status,
                },
            )

            logger.info(
                "Scoring complete: script=%s status=%s auto_score=%.2f had_ocr=%s",
                script_id, new_status, result.objective_auto_score, result.had_ocr,
            )

            return {
                "script_id":            script_id,
                "status":               new_status,
                "question_count":       len(result.scores),
                "objective_auto_score": result.objective_auto_score,
                "had_ocr":              result.had_ocr,
            }

        except Exception as exc:
            logger.error(
                "Scoring failed for script=%s: %s", script_id, exc, exc_info=True
            )
            try:
                await ScriptRepository.set_failed(script_uuid, db=session)
                await session.commit()
            except Exception:
                pass
            try:
                await AuditService.log(
                    AuditEventType.SCRIPT_SCORING_FAILED,
                    actor_user_id=None,
                    actor_role="SYSTEM",
                    tenant_id=None,
                    schema_name=schema_name,
                    target_entity="scanned_script",
                    target_id=script_id,
                    metadata={"error": str(exc)[:500]},
                )
            except Exception:
                pass
            raise
