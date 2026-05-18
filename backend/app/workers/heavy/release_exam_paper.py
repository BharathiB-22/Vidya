"""
Celery heavy-queue task: release (auto-decrypt) a sealed exam paper (M08).

This task is scheduled with an ETA equal to the paper's release_at timestamp
and runs automatically when the exam time arrives.

Flow:
  1. Load ExamPaper from DB.
  2. Verify status == SEALED and release_at <= now.
  3. Call ExamService.release() → status SEALED → RELEASED.
  4. Audit EXAM_PAPER_RELEASED.

On failure:
  - Re-raise so Celery marks FAILED and retries.
  - Operators can manually trigger retry via Celery admin or re-seal.
"""
import asyncio
import logging
import sys

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m08.release_exam_paper")

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
    name="app.workers.heavy.release_exam_paper",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def release_exam_paper(
    *,
    job_id:      str,
    paper_id:    str,
    schema_name: str,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_release(
            paper_id=paper_id,
            schema_name=schema_name,
        )
    )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_release(*, paper_id: str, schema_name: str) -> dict:
    from uuid import UUID
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m08_exam_setter.service import ExamService

    engine = _get_async_engine()
    paper_uuid = UUID(paper_id)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(text(f"SET search_path TO {schema_name}, public"))

        paper = await ExamService.release(paper_uuid, schema_name=schema_name, db=session)

        await AuditService.log(
            AuditEventType.EXAM_PAPER_RELEASED,
            actor_user_id=None,
            actor_role="SYSTEM",
            tenant_id=None,
            schema_name=schema_name,
            target_entity="exam_paper",
            target_id=paper_id,
            metadata={"title": paper.title, "released_at": str(paper.released_at)},
        )

        logger.info("Paper released: paper=%s", paper_id)
        return {"paper_id": paper_id, "status": paper.status}
