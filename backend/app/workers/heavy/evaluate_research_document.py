"""
Celery heavy-queue task: evaluate a research document (M07).

Flow:
  1. Load ResearchDocument + parent ResearchProblem from tenant schema.
  2. Set document status → EVALUATING.
  3. Download and extract document text (S3/MinIO presigned URL or mock in dev).
  4. Run M06 AI content scan (reuse without modification).
  5. Run M06 plagiarism check against sibling documents in cohort.
  6. Run document format compliance check (sections, word count, citations).
  7. Call LLM clarity scoring via document_eval.evaluate_document().
  8. Write evaluation_report + scores to ResearchDocument; set status → EVALUATED.
  9. Commit. Audit RESEARCH_DOCUMENT_AI_EVALUATED.

On failure:
  - session.rollback() to clear any failed transaction.
  - Revert document status → SUBMITTED (allows re-queue).
  - Audit RESEARCH_DOCUMENT_EVAL_FAILED.
  - Re-raise so Celery marks the task FAILED.

Human gate: status NEVER advances past EVALUATED here.
Guide must call /documents/{id}/review explicitly.
"""
import asyncio
import logging
import sys
from uuid import UUID

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m07.evaluate_research_document")


def _make_async_engine(schema_name: str):
    """Create a fresh async engine with NullPool, pre-configured for the tenant schema.

    Two reasons for this design:

    1. NullPool (BUG-006): asyncpg binds pool Futures to the event loop that
       created them.  Celery calls asyncio.run() per task → new loop each time.
       A pooled engine from a prior invocation holds stale Futures → RuntimeError.

    2. server_settings search_path (BUG-007): SQLAlchemy releases the underlying
       connection back to the pool after each session.commit().  With NullPool the
       connection is destroyed; the next query gets a fresh connection whose
       search_path defaults to 'public'.  Passing search_path via asyncpg
       server_settings ensures every new connection is born with the correct
       tenant schema — no explicit SET command required after each commit.
    """
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.config import settings
    return create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": f"{schema_name},public"}},
    )


@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.evaluate_research_document",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def evaluate_research_document(
    *,
    job_id: str,
    document_id: str,
    schema_name: str,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_document_evaluation(
            document_id=UUID(document_id),
            schema_name=schema_name,
        )
    )


async def _run_document_evaluation(document_id: UUID, schema_name: str) -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m07_research_supervision.models import DocumentStatus
    from app.modules.m07_research_supervision.repository import (
        DocumentRepository,
        ProblemRepository,
    )
    from app.modules.m07_research_supervision.document_eval import evaluate_document

    if not schema_name or not schema_name.startswith("tenant_"):
        raise ValueError(
            f"Invalid schema_name {schema_name!r}: expected a non-empty 'tenant_<slug>' string."
        )

    engine = _make_async_engine(schema_name)

    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            await session.execute(text(f"SET search_path TO {schema_name}, public"))

            try:
                # 1. Load document + problem
                doc = await DocumentRepository.get_by_id(document_id, db=session)
                if doc is None:
                    raise ValueError(
                        f"ResearchDocument {document_id} not found in {schema_name!r}."
                    )

                problem = await ProblemRepository.get_by_id(doc.research_problem_id, db=session)
                if problem is None:
                    raise ValueError(
                        f"Parent ResearchProblem not found for doc {document_id}."
                    )

                # 2. Mark as EVALUATING
                await DocumentRepository.set_status(
                    document_id, DocumentStatus.EVALUATING.value, db=session
                )
                await session.commit()

                # 3. Fetch document text (dev: use abstract; prod: download from S3)
                content_text = _fetch_document_text(
                    doc.file_url, doc.file_name, problem.abstract
                )

                # 4. Collect cohort as (doc_id, text) tuples for plagiarism check
                sibling_docs = await DocumentRepository.list_for_problem(
                    doc.research_problem_id, db=session
                )
                corpus_texts = [
                    (d.id, _fetch_document_text(d.file_url, d.file_name, ""))
                    for d in sibling_docs
                    if d.id != document_id and d.status not in (
                        DocumentStatus.SUBMITTED.value, DocumentStatus.EVALUATING.value
                    )
                ]

                # 5. Run full evaluation pipeline
                result = await evaluate_document(
                    title=problem.title,
                    content_text=content_text,
                    corpus_texts=corpus_texts,
                )

                # 6. Write result — status → EVALUATED (human gate holds here)
                await DocumentRepository.set_eval_result(
                    document_id,
                    plagiarism_score=result.plagiarism_score,
                    ai_content_score=result.ai_content_score,
                    format_score=result.format_score,
                    clarity_score=result.clarity_score,
                    evaluation_report=result.evaluation_report,
                    ai_model=result.ai_model,
                    prompt_hash=result.prompt_hash,
                    db=session,
                )
                await session.commit()

                # 7. Audit
                await AuditService.log(
                    AuditEventType.RESEARCH_DOCUMENT_AI_EVALUATED,
                    actor_user_id=None,
                    actor_role="SYSTEM",
                    tenant_id=None,
                    schema_name=schema_name,
                    target_entity="research_document",
                    target_id=str(document_id),
                    metadata={
                        "plagiarism_score": result.plagiarism_score,
                        "ai_content_score": result.ai_content_score,
                        "format_score":     result.format_score,
                        "clarity_score":    result.clarity_score,
                        "ai_model":         result.ai_model,
                    },
                )

                logger.info(
                    "Document evaluated: doc=%s plagiarism=%.2f ai_content=%.2f "
                    "format=%.2f clarity=%.2f",
                    document_id,
                    result.plagiarism_score,
                    result.ai_content_score,
                    result.format_score,
                    result.clarity_score,
                )

                return {
                    "document_id":      str(document_id),
                    "plagiarism_score": result.plagiarism_score,
                    "ai_content_score": result.ai_content_score,
                    "format_score":     result.format_score,
                    "clarity_score":    result.clarity_score,
                }

            except Exception as exc:
                failure_reason = f"{type(exc).__name__}: {exc}"
                logger.error(
                    "Document evaluation failed for %s: %s",
                    document_id, failure_reason, exc_info=True,
                )

                # rollback clears any partial transaction before the reset write
                try:
                    await session.rollback()
                    await DocumentRepository.set_status(
                        document_id, DocumentStatus.SUBMITTED.value, db=session
                    )
                    await session.commit()
                except Exception as mark_exc:
                    logger.error(
                        "Could not revert document %s to SUBMITTED: %s",
                        document_id, mark_exc,
                    )

                try:
                    await AuditService.log(
                        AuditEventType.RESEARCH_DOCUMENT_EVAL_FAILED,
                        actor_user_id=None,
                        actor_role="SYSTEM",
                        tenant_id=None,
                        schema_name=schema_name,
                        target_entity="research_document",
                        target_id=str(document_id),
                        metadata={"error": failure_reason},
                    )
                except Exception:
                    pass

                raise

    finally:
        await engine.dispose()


def _fetch_document_text(file_url: str | None, file_name: str | None, fallback: str) -> str:
    """
    In dev mode (no real S3), return the fallback text (problem abstract).
    In production this would download the PDF from MinIO and extract text.
    """
    if not file_url:
        return fallback or "[No document content available]"
    from app.config import settings
    if settings.ENVIRONMENT != "production":
        return fallback or f"[Dev: document at {file_url}]"
    try:
        import urllib.request
        with urllib.request.urlopen(file_url, timeout=30) as resp:
            raw = resp.read()
        return raw.decode("utf-8", errors="ignore")[:50_000]
    except Exception as exc:
        logger.warning("Failed to fetch document %s: %s", file_url, exc)
        return fallback or "[Document download failed]"
