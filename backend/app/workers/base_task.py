import json
import logging

from celery import Task

logger = logging.getLogger("vidya.worker")

# ---------------------------------------------------------------------------
# Transient exception set — safe to retry without human intervention.
#
# Subclasses narrow this to task-specific exceptions, e.g.:
#   autoretry_for = (google.api_core.exceptions.ResourceExhausted,
#                    google.api_core.exceptions.ServiceUnavailable)   # AI tasks
#   autoretry_for = (smtplib.SMTPException, ConnectionError)          # email tasks
# ---------------------------------------------------------------------------
_TRANSIENT_ERRORS: tuple = (
    ConnectionError,   # network-level drops (Redis, DB, external APIs)
    TimeoutError,      # socket / request timeouts
    OSError,           # low-level I/O failures
)

# Module-level sync engine — created once per worker process, reused across tasks.
_sync_engine = None


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        from sqlalchemy import create_engine
        from app.config import settings
        _sync_engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)
    return _sync_engine


class VidyaTask(Task):
    """
    Base task class for all Vidya background jobs.

    Provides:
    - Consistent retry policy (exponential backoff with jitter).
    - Automatic task_jobs row updates on RUNNING / SUCCESS / FAILED transitions.
    - Retry logging via on_retry.

    Usage
    -----
    Register a light task::

        @celery_app.task(base=VidyaTask)
        def send_notification(*, job_id, user_id, message):
            ...

    Override retry policy for AI tasks::

        @celery_app.task(
            base=VidyaTask,
            autoretry_for=(GeminiRateLimitError, ServiceUnavailable),
            max_retries=5,
            retry_backoff_max=300,
        )
        def generate_syllabus(*, job_id, tenant_id, course_id):
            ...

    The caller must pass ``job_id`` as a keyword argument so the hooks can
    locate the corresponding task_jobs row::

        generate_syllabus.apply_async(
            kwargs={"job_id": str(job.id), "course_id": str(course_id)}
        )
    """

    abstract = True

    # ------------------------------------------------------------------
    # Retry policy
    # Celery reads these class attributes before executing the task body.
    # Subclasses can override any of them at the @task() decorator level.
    # ------------------------------------------------------------------

    autoretry_for: tuple = _TRANSIENT_ERRORS

    retry_backoff: bool = True
    retry_backoff_max: int = 600   # cap per-attempt delay at 10 minutes
    retry_jitter: bool = True      # randomise delay to avoid thundering herd

    max_retries: int = 3
    retry_kwargs: dict = {"max_retries": 3}   # forwarded to self.retry() by autoretry

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def before_start(self, task_id, args, kwargs):
        """Mark the job RUNNING when the worker picks it up."""
        job_id = kwargs.get("job_id")
        if job_id:
            self._write_status(job_id, "RUNNING")

    def on_success(self, retval, task_id, args, kwargs):
        """Mark the job SUCCESS and persist the return value."""
        job_id = kwargs.get("job_id")
        if job_id:
            self._write_status(job_id, "SUCCESS", result=retval)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Mark the job FAILED (called only after all retries are exhausted)."""
        job_id = kwargs.get("job_id")
        if job_id:
            self._write_status(job_id, "FAILED", error=str(exc))

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Log each retry attempt; job status stays RUNNING during retries."""
        job_id = kwargs.get("job_id")
        logger.warning(
            "VidyaTask retry: job=%s task=%s attempt=%d/%d error=%s",
            job_id,
            self.name,
            self.request.retries,
            self.max_retries,
            exc,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_status(
        self,
        job_id: str,
        status: str,
        *,
        result=None,
        error: str | None = None,
    ) -> None:
        """Update public.task_jobs via a synchronous psycopg2 connection.

        Uses raw SQL so the worker process has no dependency on the async
        SQLAlchemy session used by FastAPI.  Failures are swallowed and
        logged — a status-write error must never crash the worker or
        suppress the real task result.
        """
        from sqlalchemy import text

        set_parts = ["status = :status"]
        params: dict = {"status": status, "job_id": str(job_id)}

        if status == "RUNNING":
            set_parts.append("started_at = now()")

        if status in ("SUCCESS", "FAILED", "CANCELLED"):
            set_parts.append("completed_at = now()")

        if result is not None:
            set_parts.append("result = :result::jsonb")
            params["result"] = json.dumps(result, default=str)

        if error is not None:
            set_parts.append("error = :error")
            params["error"] = error

        sql = f"UPDATE public.task_jobs SET {', '.join(set_parts)} WHERE id = :job_id::uuid"

        try:
            engine = _get_sync_engine()
            with engine.connect() as conn:
                with conn.begin():
                    conn.execute(text(sql), params)
        except Exception:
            logger.exception(
                "VidyaTask: failed to write status %s for job %s", status, job_id
            )
