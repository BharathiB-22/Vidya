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
