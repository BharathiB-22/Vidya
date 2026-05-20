import asyncio
import logging
import time
from typing import Optional

from sqlalchemy import text

from app.config import settings
from app.database import AsyncSessionLocal
from app.core.monitoring.prometheus_metrics import dependency_health

logger = logging.getLogger("vidya.error")

_HEALTH_STATUS_TO_GAUGE = {"healthy": 1.0, "unhealthy": 0.0, "skipped": -1.0}


class HealthCheckResult:
    """Result of a single health check."""

    def __init__(
        self, service: str, status: str, latency_ms: float, error_msg: Optional[str] = None
    ):
        self.service = service
        self.status = status
        self.latency_ms = latency_ms
        self.error_msg = error_msg

    def to_dict(self) -> dict:
        return {
            "service": self.service,
            "status": self.status,
            "latency_ms": round(self.latency_ms, 2),
            "error_msg": self.error_msg,
        }


class HealthService:
    """Health check service for Kubernetes probes."""

    @staticmethod
    async def check_db_connection(
        timeout: float = 2.0,
    ) -> HealthCheckResult:
        """Check PostgreSQL connection."""
        start = time.perf_counter()
        try:
            async with AsyncSessionLocal() as session:
                await asyncio.wait_for(
                    session.execute(text("SELECT 1")),
                    timeout=timeout,
                )
            latency_ms = (time.perf_counter() - start) * 1000
            return HealthCheckResult("db", "healthy", latency_ms)
        except asyncio.TimeoutError:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.warning("Database health check timeout after %.1fms", latency_ms)
            return HealthCheckResult(
                "db",
                "unhealthy",
                latency_ms,
                error_msg="Connection timeout",
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.warning("Database health check failed: %s", exc)
            return HealthCheckResult(
                "db",
                "unhealthy",
                latency_ms,
                error_msg=str(exc),
            )

    @staticmethod
    async def check_redis_connection(
        timeout: float = 2.0,
    ) -> HealthCheckResult:
        """Check Redis connection via socket ping."""
        start = time.perf_counter()
        try:
            import socket
            from urllib.parse import urlparse

            redis_url = urlparse(settings.REDIS_URL)
            host = redis_url.hostname or "localhost"
            port = redis_url.port or 6379

            def _ping_redis():
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                try:
                    sock.connect((host, port))
                    sock.close()
                    return True
                except Exception:
                    return False

            loop = asyncio.get_event_loop()
            connected = await asyncio.wait_for(
                loop.run_in_executor(None, _ping_redis),
                timeout=timeout,
            )

            if connected:
                latency_ms = (time.perf_counter() - start) * 1000
                return HealthCheckResult("redis", "healthy", latency_ms)
            else:
                latency_ms = (time.perf_counter() - start) * 1000
                return HealthCheckResult(
                    "redis",
                    "unhealthy",
                    latency_ms,
                    error_msg="Connection refused",
                )
        except asyncio.TimeoutError:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.warning("Redis health check timeout after %.1fms", latency_ms)
            return HealthCheckResult(
                "redis",
                "unhealthy",
                latency_ms,
                error_msg="Connection timeout",
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.warning("Redis health check failed: %s", exc)
            return HealthCheckResult(
                "redis",
                "unhealthy",
                latency_ms,
                error_msg=str(exc),
            )

    @staticmethod
    async def check_s3_connection(
        timeout: float = 2.0,
    ) -> HealthCheckResult:
        """Check S3/MinIO connection."""
        start = time.perf_counter()
        try:
            import boto3

            def _check_s3():
                client = boto3.client(
                    "s3",
                    endpoint_url=settings.S3_ENDPOINT,
                    aws_access_key_id=settings.S3_ACCESS_KEY,
                    aws_secret_access_key=settings.S3_SECRET_KEY,
                    region_name=settings.S3_REGION,
                    verify=settings.S3_USE_SSL,
                )
                client.head_bucket(Bucket=settings.S3_BUCKET)

            loop = asyncio.get_event_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, _check_s3),
                timeout=timeout,
            )
            latency_ms = (time.perf_counter() - start) * 1000
            return HealthCheckResult("s3", "healthy", latency_ms)
        except asyncio.TimeoutError:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.warning("S3 health check timeout after %.1fms", latency_ms)
            return HealthCheckResult(
                "s3",
                "unhealthy",
                latency_ms,
                error_msg="Connection timeout",
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.warning("S3 health check failed: %s", exc)
            return HealthCheckResult(
                "s3",
                "unhealthy",
                latency_ms,
                error_msg=str(exc),
            )

    @staticmethod
    async def check_qdrant_connection(
        timeout: float = 2.0,
    ) -> HealthCheckResult:
        """Check Qdrant vector database connection.

        Skipped (status='skipped') when QDRANT_URL is empty — Qdrant is optional
        and its absence must not fail the readiness probe.
        """
        if not settings.QDRANT_URL:
            return HealthCheckResult("qdrant", "skipped", 0.0)

        start = time.perf_counter()
        try:
            import httpx

            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(
                    f"{settings.QDRANT_URL.rstrip('/')}/healthz"
                )
                if resp.status_code == 200:
                    latency_ms = (time.perf_counter() - start) * 1000
                    return HealthCheckResult("qdrant", "healthy", latency_ms)
                else:
                    latency_ms = (time.perf_counter() - start) * 1000
                    return HealthCheckResult(
                        "qdrant",
                        "unhealthy",
                        latency_ms,
                        error_msg=f"HTTP {resp.status_code}",
                    )
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.warning("Qdrant health check failed: %s", exc)
            return HealthCheckResult(
                "qdrant",
                "unhealthy",
                latency_ms,
                error_msg=str(exc),
            )

    @staticmethod
    async def check_all(timeout: float = 2.0) -> tuple[list[HealthCheckResult], bool]:
        """Check all services in parallel and update Prometheus dependency gauges.

        Returns:
            (list of HealthCheckResult, all_healthy: bool)

        Qdrant is optional — 'skipped' status is treated as healthy for the
        purposes of all_healthy (empty QDRANT_URL => skipped, not failed).
        """
        results = await asyncio.gather(
            HealthService.check_db_connection(timeout),
            HealthService.check_redis_connection(timeout),
            HealthService.check_s3_connection(timeout),
            HealthService.check_qdrant_connection(timeout),
        )

        for result in results:
            dependency_health.labels(service=result.service).set(
                _HEALTH_STATUS_TO_GAUGE.get(result.status, 0.0)
            )

        all_healthy = all(r.status in ("healthy", "skipped") for r in results)
        return list(results), all_healthy
