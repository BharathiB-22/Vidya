import json
import logging

from celery import Task

from app.core.monitoring import request_id_ctx

logger = logging.getLogger("vidya.worker")

_TRANSIENT_ERRORS: tuple = (
    ConnectionError,
    TimeoutError,
    OSError,
)

_sync_engine = None


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        from sqlalchemy import create_engine
        from app.config import settings
        _sync_engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)
    return _sync_engine


class VidyaTask(Task):
    abstract = True

    autoretry_for: tuple = _TRANSIENT_ERRORS
    retry_backoff: bool = True
    retry_backoff_max: int = 600
    retry_jitter: bool = True
    max_retries: int = 3
    retry_kwargs: dict = {"max_retries": 3}

    def before_start(self, task_id, args, kwargs):
        job_id = kwargs.get("job_id")
        if job_id:
            self._write_status(job_id, "RUNNING")

    def on_success(self, retval, task_id, args, kwargs):
        job_id = kwargs.get("job_id")
        if job_id:
            self._write_status(job_id, "SUCCESS", result=retval)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        job_id = kwargs.get("job_id")
        if job_id:
            self._write_status(job_id, "FAILED", error=str(exc))

        revert_table  = kwargs.get("_revert_table")
        revert_pk     = kwargs.get("_revert_pk")
        revert_schema = kwargs.get("_revert_schema")
        revert_status = kwargs.get("_revert_status")
        if revert_table and revert_pk and revert_schema and revert_status:
            self._revert_entity_status(revert_table, revert_pk, revert_schema, revert_status)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        job_id = kwargs.get("job_id")
        request_id = kwargs.get("request_id")

        if request_id:
            request_id_ctx.set(request_id)

        logger.warning(
            "VidyaTask retry: job=%s task=%s attempt=%d/%d error=%s",
            job_id,
            self.name,
            self.request.retries,
            self.max_retries,
            exc,
            extra={
                "event": "task_retry",
                "task_id": task_id,
                "task_name": self.name,
                "request_id": request_id,
                "job_id": str(job_id) if job_id else None,
                "attempt": self.request.retries,
                "max_retries": self.max_retries,
                "exception": str(exc),
            },
        )

    def _revert_entity_status(
        self,
        table: str,
        pk: str,
        schema_name: str,
        status: str,
    ) -> None:
        from sqlalchemy import text

        sql = (
            f"UPDATE {schema_name}.{table} "
            "SET status = :status, updated_at = now() "
            "WHERE id = CAST(:pk AS uuid)"
        )
        try:
            engine = _get_sync_engine()
            with engine.connect() as conn:
                with conn.begin():
                    conn.execute(text(sql), {"status": status, "pk": pk})
            logger.info(
                "VidyaTask: reverted %s.%s id=%s to %s",
                schema_name, table, pk, status,
            )
        except Exception:
            logger.exception(
                "VidyaTask: failed to revert %s.%s id=%s to %s",
                schema_name, table, pk, status,
            )

    def _write_status(
        self,
        job_id: str,
        status: str,
        *,
        result=None,
        error: str | None = None,
    ) -> None:
        from sqlalchemy import text

        set_parts = ["status = :status"]
        params: dict = {"status": status, "job_id": str(job_id)}

        if status == "RUNNING":
            set_parts.append("started_at = now()")
        if status in ("SUCCESS", "FAILED", "CANCELLED"):
            set_parts.append("completed_at = now()")
        if result is not None:
            set_parts.append("result = CAST(:result AS jsonb)")
            params["result"] = json.dumps(result, default=str)
        if error is not None:
            set_parts.append("error = :error")
            params["error"] = error

        sql = f"UPDATE public.task_jobs SET {', '.join(set_parts)} WHERE id = CAST(:job_id AS uuid)"

        try:
            engine = _get_sync_engine()
            with engine.connect() as conn:
                with conn.begin():
                    conn.execute(text(sql), params)
        except Exception:
            logger.exception(
                "VidyaTask: failed to write status %s for job %s", status, job_id
            )
