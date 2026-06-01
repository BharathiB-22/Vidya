from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class HealthCheckResult(BaseModel):
    """Result of a single service health check."""

    service: str = Field(..., description="Service name (db, redis, s3, qdrant)")
    status: str = Field(..., description="'healthy' or 'unhealthy'")
    latency_ms: float = Field(..., description="Check duration in milliseconds")
    error_msg: Optional[str] = Field(None, description="Error message if unhealthy")

    model_config = {"json_schema_extra": {"example": {"service": "db", "status": "healthy", "latency_ms": 12.5, "error_msg": None}}}


class HealthStatus(BaseModel):
    """Response for readiness probe endpoint (/ready)."""

    ready: bool = Field(..., description="True if all services healthy")
    timestamp: datetime = Field(..., description="Timestamp of health check")
    checks: dict[str, str] = Field(..., description="Service -> status mapping")

    model_config = {
        "json_schema_extra": {
            "example": {
                "ready": True,
                "timestamp": "2026-05-07T14:23:45Z",
                "checks": {"db": "healthy", "redis": "healthy", "s3": "healthy"},
            }
        }
    }


class LivenessResponse(BaseModel):
    """Response for liveness probe endpoint (/healthz)."""

    status: str = Field(..., description="'ok' if app is running")
    environment: str = Field(..., description="Deployment environment")
    timestamp: datetime = Field(..., description="Timestamp of liveness check")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "ok",
                "environment": "development",
                "timestamp": "2026-05-07T14:23:45Z",
            }
        }
    }


class PlatformDiagnosticService(BaseModel):
    service:    str
    label:      str
    status:     str            # healthy | unhealthy | warning | skipped
    latency_ms: float
    detail:     Optional[str] = None
    error_msg:  Optional[str] = None


class QueueDiagnostics(BaseModel):
    pending:        int
    running:        int
    completed:      int
    failed:         int
    failed_24h:     int
    total_24h:      int
    celery_pending: int
    celery_running: int
    heavy_pending:  int
    heavy_running:  int
    workers_online: int


class AIProviderDiagnostic(BaseModel):
    name:         str
    provider_key: str
    active:       bool
    configured:   bool
    model:        str
    status:       str          # ready | not_configured


class PlatformHealthResponse(BaseModel):
    generated_at: datetime
    all_healthy:  bool
    system:       list[PlatformDiagnosticService]
    workers:      list[PlatformDiagnosticService]
    queue:        QueueDiagnostics
    ai:           list[AIProviderDiagnostic]


class MetricsResponse(BaseModel):
    """Response for metrics endpoint (/metrics). Skeleton for future Prometheus integration."""

    request_count: int = Field(..., description="Total HTTP requests since startup")
    request_latency_p50_ms: float = Field(..., description="50th percentile latency")
    request_latency_p95_ms: float = Field(..., description="95th percentile latency")
    request_latency_p99_ms: float = Field(..., description="99th percentile latency")
    task_queue_depth: int = Field(..., description="Celery tasks pending")
    db_connection_pool_size: int = Field(..., description="Active DB connections")
    timestamp: datetime = Field(..., description="Timestamp of metrics collection")

    model_config = {
        "json_schema_extra": {
            "example": {
                "request_count": 1234,
                "request_latency_p50_ms": 45.2,
                "request_latency_p95_ms": 120.5,
                "request_latency_p99_ms": 250.3,
                "task_queue_depth": 12,
                "db_connection_pool_size": 5,
                "timestamp": "2026-05-07T14:23:45Z",
            }
        }
    }
