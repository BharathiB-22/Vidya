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

from app.database import tenant_schema_scope
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
        # Re-apply the schema at the START OF EVERY TRANSACTION, not once per
        # session. A commit hands this connection back — NullPool closes it, a pool
        # recycles it — so anything after the first commit would otherwise run with
        # search_path = public, and a pooled connection could arrive still carrying
        # ANOTHER tenant's search_path. A commit cannot undo a per-BEGIN SET LOCAL.
        from app.database import bind_tenant_search_path
        bind_tenant_search_path(_async_engine)
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
    # Which tenant every transaction in this task belongs to. Held for the whole
    # run and dropped at the end of it: a worker process is long-lived and serves
    # every tenant in turn, and a schema left set is one the next task inherits.
    with tenant_schema_scope(schema_name):
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
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m08_exam_setter.service import ExamService

    engine = _get_async_engine()
    paper_uuid = UUID(paper_id)

    async with AsyncSession(engine, expire_on_commit=False) as session:
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
