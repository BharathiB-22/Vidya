import re

from prometheus_client import Counter, Gauge, Histogram

# --- HTTP ---
http_requests_total = Counter(
    "vidya_http_requests_total",
    "Total HTTP requests processed",
    ["method", "path", "status_code"],
)

http_request_duration_seconds = Histogram(
    "vidya_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

http_requests_in_progress = Gauge(
    "vidya_http_requests_in_progress",
    "HTTP requests currently being processed",
    ["method", "path"],
)

auth_failures_total = Counter(
    "vidya_auth_failures_total",
    "Total authentication failures (HTTP 401 responses)",
    ["path"],
)

# --- Celery ---
celery_tasks_total = Counter(
    "vidya_celery_tasks_total",
    "Total Celery tasks by name and terminal state",
    ["task_name", "state"],
)

celery_task_duration_seconds = Histogram(
    "vidya_celery_task_duration_seconds",
    "Celery task duration from prerun to postrun in seconds",
    ["task_name"],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0],
)

celery_queue_depth = Gauge(
    "vidya_celery_queue_depth",
    "Current depth of a Celery queue (updated by periodic beat task)",
    ["queue_name"],
)

# --- Dependency health ---
dependency_health = Gauge(
    "vidya_dependency_health",
    "Dependency health status: 1=healthy, 0=unhealthy, -1=skipped",
    ["service"],
)

# --- Path normalisation ---
_UUID_RE = re.compile(
    r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_INT_ID_RE = re.compile(r"/\d+(?=/|$)")


def normalize_path(path: str) -> str:
    """Replace UUID and integer path segments with {id} to cap label cardinality."""
    path = _UUID_RE.sub("/{id}", path)
    path = _INT_ID_RE.sub("/{id}", path)
    return path
