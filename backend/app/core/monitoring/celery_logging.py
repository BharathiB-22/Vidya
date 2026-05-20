import logging
import time

from celery.signals import task_failure, task_postrun, task_prerun

from app.core.monitoring import mask_sensitive_fields, request_id_ctx
from app.core.monitoring.prometheus_metrics import (
    celery_task_duration_seconds,
    celery_tasks_total,
)

celery_logger = logging.getLogger("vidya.celery")

# Task start times keyed by task_id — used to compute durations in on_task_end.
_task_start_times: dict[str, float] = {}


def setup_celery_logging() -> None:
    """Wire Celery signals to structured logging and Prometheus metrics."""
    task_prerun.connect(on_task_start, weak=False)
    task_postrun.connect(on_task_end, weak=False)
    task_failure.connect(on_task_failure, weak=False)


def on_task_start(sender=None, task_id=None, args=None, kwargs=None, **extra_kwargs) -> None:
    """Log task start event and record start time for duration tracking."""
    request_id = kwargs.get("request_id") if kwargs else None
    job_id = kwargs.get("job_id") if kwargs else None

    if request_id:
        request_id_ctx.set(request_id)

    if task_id:
        _task_start_times[task_id] = time.monotonic()

    args_summary = _summarize_args(args or ())
    kwargs_summary = _summarize_kwargs(kwargs or {})

    celery_logger.info(
        f"Task started: {sender.name}",
        extra={
            "event": "task_start",
            "task_id": task_id,
            "task_name": sender.name,
            "queue": sender.queue if hasattr(sender, "queue") else "unknown",
            "request_id": request_id,
            "job_id": str(job_id) if job_id else None,
            "args": args_summary,
            "kwargs": kwargs_summary,
        },
    )


def on_task_end(sender=None, task_id=None, state=None, retval=None, args=None, kwargs=None, **extra_kwargs) -> None:
    """Log task completion, record duration and state counter in Prometheus."""
    request_id = kwargs.get("request_id") if kwargs else None
    job_id = kwargs.get("job_id") if kwargs else None

    if request_id:
        request_id_ctx.set(request_id)

    start = _task_start_times.pop(task_id, None) if task_id else None
    if start is not None:
        duration_s = time.monotonic() - start
        celery_task_duration_seconds.labels(task_name=sender.name).observe(duration_s)

    if state is not None:
        celery_tasks_total.labels(task_name=sender.name, state=state).inc()

    result_summary = _summarize_result(retval)

    celery_logger.info(
        f"Task completed: {sender.name} [{state}]",
        extra={
            "event": "task_end",
            "task_id": task_id,
            "task_name": sender.name,
            "state": state,
            "request_id": request_id,
            "job_id": str(job_id) if job_id else None,
            "result": result_summary,
        },
    )


def on_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, **extra_kwargs) -> None:
    """Log task failure event. Counter increment handled by on_task_end."""
    request_id = kwargs.get("request_id") if kwargs else None
    job_id = kwargs.get("job_id") if kwargs else None

    if request_id:
        request_id_ctx.set(request_id)

    celery_logger.error(
        f"Task failed: {sender.name}",
        extra={
            "event": "task_failure",
            "task_id": task_id,
            "task_name": sender.name,
            "request_id": request_id,
            "job_id": str(job_id) if job_id else None,
            "exception_type": type(exception).__name__ if exception else "Unknown",
            "exception_message": str(exception) if exception else None,
            "traceback": traceback,
            "retries": getattr(sender.request, "retries", 0) if hasattr(sender, "request") else 0,
            "max_retries": sender.max_retries if hasattr(sender, "max_retries") else None,
        },
        exc_info=einfo,
    )


def _summarize_args(args: tuple) -> list:
    """Create a masked summary of task args."""
    if not args:
        return []
    summary = []
    for arg in args[:3]:
        if isinstance(arg, str) and len(arg) > 100:
            summary.append(f"{type(arg).__name__}[{len(arg)} chars]")
        elif isinstance(arg, (dict, list)):
            summary.append(f"{type(arg).__name__}[{len(arg)} items]")
        else:
            summary.append(type(arg).__name__)
    return summary


def _summarize_kwargs(kwargs: dict) -> dict:
    """Create a masked summary of task kwargs."""
    if not kwargs:
        return {}

    summary = {}
    skip_keys = {"request_id", "job_id"}

    for key, value in kwargs.items():
        if key in skip_keys:
            summary[key] = value
            continue

        if isinstance(value, str) and len(value) > 100:
            summary[key] = f"str[{len(value)} chars]"
        elif isinstance(value, (dict, list)):
            summary[key] = f"{type(value).__name__}[{len(value)} items]"
        elif isinstance(value, bytes):
            summary[key] = f"bytes[{len(value)} bytes]"
        else:
            summary[key] = type(value).__name__

    return mask_sensitive_fields(summary)


def _summarize_result(retval) -> str:
    """Create a masked summary of task result."""
    if retval is None:
        return "None"
    if isinstance(retval, str) and len(retval) > 200:
        return f"str[{len(retval)} chars]"
    if isinstance(retval, (dict, list)):
        return f"{type(retval).__name__}[{len(retval)} items]"
    if isinstance(retval, bytes):
        return f"bytes[{len(retval)} bytes]"
    return str(type(retval).__name__)
