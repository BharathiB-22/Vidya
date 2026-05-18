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
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m07_research_supervision.models import (
        DocumentStatus,
        ResearchDocument,
        ResearchProblem,
    )
    from app.modules.m07_research_supervision.repository import (
        DocumentRepository,
        ProblemRepository,
    )
    from app.modules.m07_research_supervision.document_eval import evaluate_document

    engine = _get_async_engine()

    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(text(f"SET search_path TO {schema_name}, public"))

        doc = await DocumentRepository.get_by_id(document_id, db=session)
        if doc is None:
            raise ValueError(f"ResearchDocument {document_id} not found in {schema_name!r}.")

        problem = await ProblemRepository.get_by_id(doc.research_problem_id, db=session)
        if problem is None:
            raise ValueError(f"Parent ResearchProblem not found for doc {document_id}.")

        # 1. Mark as EVALUATING
        await DocumentRepository.set_status(document_id, DocumentStatus.EVALUATING.value, db=session)
        await session.commit()

        # 2. Fetch document text (dev: use abstract as surrogate; prod: download from S3)
        content_text = _fetch_document_text(doc.file_url, doc.file_name, problem.abstract)

        # 3. Collect cohort texts (other documents for same problem, for plagiarism)
        sibling_docs = await DocumentRepository.list_for_problem(
            doc.research_problem_id, db=session
        )
        corpus_texts = [
            _fetch_document_text(d.file_url, d.file_name, "")
            for d in sibling_docs
            if d.id != document_id and d.status not in (
                DocumentStatus.SUBMITTED.value, DocumentStatus.EVALUATING.value
            )
        ]

        # 4. Run full evaluation pipeline
        result = await evaluate_document(
            title=problem.title,
            content_text=content_text,
            corpus_texts=corpus_texts,
        )

        # 5. Write result — status → EVALUATED (human gate holds here)
        await DocumentRepository.set_eval_result(
            document_id,
            plagiarism_score=result.plagiarism_score,
            ai_content_score=result.ai_content_score,
            format_score=result.format_score,
            clarity_score=result.clarity_score,
            evaluation_report=result.evaluation_report,
            ai_model=result.ai_model,
            prompt_hash=result.prompt_hash,
            new_status=DocumentStatus.EVALUATED.value,
            db=session,
        )
        await session.commit()

        # 6. Audit (AI-advisory only)
        await AuditService.log(
            AuditEventType.RESEARCH_DOCUMENT_AI_EVALUATED,
            actor_user_id=None,
            actor_role="SYSTEM",
            tenant_id=None,
            schema_name=schema_name,
            target_entity="research_document",
            target_id=str(document_id),
            metadata={
                "plagiarism_score":  result.plagiarism_score,
                "ai_content_score":  result.ai_content_score,
                "format_score":      result.format_score,
                "clarity_score":     result.clarity_score,
                "ai_model":          result.ai_model,
            },
        )

        logger.info(
            "Document evaluated: doc=%s plagiarism=%.2f ai_content=%.2f format=%.2f clarity=%.2f",
            document_id, result.plagiarism_score, result.ai_content_score,
            result.format_score, result.clarity_score,
        )

        return {
            "document_id":      str(document_id),
            "plagiarism_score": result.plagiarism_score,
            "ai_content_score": result.ai_content_score,
            "format_score":     result.format_score,
            "clarity_score":    result.clarity_score,
        }


def _fetch_document_text(file_url: str | None, file_name: str | None, fallback: str) -> str:
    """
    In dev mode (no real S3), return the fallback text (problem abstract).
    In production this would download the PDF from MinIO and extract text.
    """
    if not file_url:
        return fallback or "[No document content available]"
    # Production: download + extract.  Dev: use fallback.
    from app.config import settings
    if settings.ENVIRONMENT != "production":
        return fallback or f"[Dev: document at {file_url}]"
    try:
        import urllib.request
        with urllib.request.urlopen(file_url, timeout=30) as resp:
            raw = resp.read()
        # Minimal text extraction — production should use a proper PDF parser
        return raw.decode("utf-8", errors="ignore")[:50_000]
    except Exception as exc:
        logger.warning("Failed to fetch document %s: %s", file_url, exc)
        return fallback or "[Document download failed]"
