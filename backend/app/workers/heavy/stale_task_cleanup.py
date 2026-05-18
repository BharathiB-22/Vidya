import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.stale_cleanup")

# Jobs still RUNNING after this many minutes are considered stuck.
_RUNNING_TIMEOUT_MINUTES = 30
# Jobs that never left PENDING after this many minutes are considered stuck.
_PENDING_TIMEOUT_MINUTES = 10


@celery_app.task(name="app.workers.heavy.stale_task_cleanup")
def stale_task_cleanup() -> dict:
    """
    Celery beat task: find task_jobs stuck in PENDING/RUNNING beyond their
    timeout, mark them FAILED, and revert entity status via payload metadata.
    """
    from sqlalchemy import create_engine, text
    from app.config import settings

    engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)
    cleaned = 0

    with engine.connect() as conn:
        with conn.begin():
            rows = conn.execute(text("""
                SELECT id, status, payload
                FROM public.task_jobs
                WHERE
                    (status = 'RUNNING'
                     AND started_at < now() - INTERVAL '30 minutes')
                    OR
                    (status = 'PENDING'
                     AND created_at < now() - INTERVAL '10 minutes')
            """)).fetchall()

            for row in rows:
                job_id = str(row.id)

                conn.execute(text("""
                    UPDATE public.task_jobs
                    SET status = 'FAILED',
                        completed_at = now(),
                        error = 'Stale task: timed out without completion'
                    WHERE id = CAST(:job_id AS uuid)
                """), {"job_id": job_id})

                payload = row.payload or {}
                revert = payload.get("revert") if isinstance(payload, dict) else {}
                if revert:
                    table  = revert.get("table")
                    pk     = revert.get("pk")
                    schema = revert.get("schema")
                    status = revert.get("status")
                    if table and pk and schema and status:
                        try:
                            conn.execute(
                                text(
                                    f"UPDATE {schema}.{table} "
                                    "SET status = :status, updated_at = now() "
                                    "WHERE id = CAST(:pk AS uuid)"
                                ),
                                {"status": status, "pk": pk},
                            )
                            logger.info(
                                "stale_cleanup: reverted %s.%s id=%s -> %s (job=%s)",
                                schema, table, pk, status, job_id,
                            )
                        except Exception:
                            logger.exception(
                                "stale_cleanup: revert failed for job=%s", job_id
                            )

                cleaned += 1
                logger.warning(
                    "stale_cleanup: job %s was %s — marked FAILED", job_id, row.status
                )

    logger.info("stale_cleanup: processed %d stale job(s)", cleaned)
    return {"cleaned": cleaned}
