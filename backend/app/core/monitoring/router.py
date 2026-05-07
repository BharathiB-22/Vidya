import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.core.monitoring.health import HealthService
from app.core.monitoring.schemas import HealthStatus, LivenessResponse, MetricsResponse

logger = logging.getLogger("vidya.access")

router = APIRouter(tags=["monitoring"])


@router.get("/healthz", response_model=LivenessResponse)
async def liveness_probe():
    """Kubernetes liveness probe endpoint.

    Returns 200 if the app is running, regardless of external service status.
    Used to detect pod crashes and restart unhealthy containers.
    """
    return LivenessResponse(
        status="ok",
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(tz=timezone.utc),
    )


@router.get("/ready", response_model=HealthStatus)
async def readiness_probe():
    """Kubernetes readiness probe endpoint.

    Returns 200 only if all critical services (DB, Redis, S3) are healthy.
    Returns 503 if any service is degraded (signals K8s to drain traffic).
    Used to detect service degradation and prevent routing traffic to unhealthy pods.
    """
    results, all_healthy = await HealthService.check_all(
        timeout=settings.HEALTH_CHECK_TIMEOUT_SECONDS
    )

    checks = {result.service: result.status for result in results}

    response = HealthStatus(
        ready=all_healthy,
        timestamp=datetime.now(tz=timezone.utc),
        checks=checks,
    )

    if not all_healthy:
        for result in results:
            if result.status == "unhealthy":
                logger.warning(
                    f"Readiness check failed: {result.service}",
                    extra={
                        "event": "readiness_check_failed",
                        "service": result.service,
                        "latency_ms": result.latency_ms,
                        "error": result.error_msg,
                    },
                )

    return response


@router.get("/metrics", response_model=MetricsResponse)
async def metrics_endpoint():
    """Metrics endpoint (skeleton for future Prometheus integration).

    Returns application metrics in JSON format.
    Currently returns placeholder values; will be enhanced with actual
    metrics collection (request counts, latencies, queue depths, etc.).
    """
    from datetime import datetime, timezone

    return MetricsResponse(
        request_count=0,
        request_latency_p50_ms=0.0,
        request_latency_p95_ms=0.0,
        request_latency_p99_ms=0.0,
        task_queue_depth=0,
        db_connection_pool_size=0,
        timestamp=datetime.now(tz=timezone.utc),
    )
