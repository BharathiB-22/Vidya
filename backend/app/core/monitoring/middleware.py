import logging
import time
import uuid
from typing import Callable

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.monitoring import request_id_ctx, tenant_id_ctx, user_id_ctx, mask_sensitive_fields
from app.core.monitoring.prometheus_metrics import (
    auth_failures_total,
    http_request_duration_seconds,
    http_requests_in_progress,
    http_requests_total,
    normalize_path,
)

logger = logging.getLogger("vidya.access")


class MonitoringMiddleware(BaseHTTPMiddleware):
    """Log all HTTP requests/responses with tenant context and correlation IDs.

    Adds X-Request-ID to response headers for distributed tracing.
    Sets context vars for request_id, tenant_id so all nested loggers
    automatically include them.
    Updates Prometheus counters, histograms, and the in-progress gauge.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = self._extract_or_generate_request_id(request)
        tenant_id = request.headers.get("X-Tenant-Slug")
        user_id = self._extract_user_id_from_jwt(request)

        request_id_ctx.set(request_id)
        tenant_id_ctx.set(tenant_id)
        user_id_ctx.set(user_id)

        method = request.method
        norm_path = normalize_path(request.url.path)
        start_time = time.perf_counter()

        http_requests_in_progress.labels(method=method, path=norm_path).inc()

        log_request_start(
            request=request,
            request_id=request_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "Unhandled exception",
                extra={
                    "exception_type": type(exc).__name__,
                    "request_id": request_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "method": method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                },
            )
            raise
        finally:
            http_requests_in_progress.labels(method=method, path=norm_path).dec()

        duration_s = time.perf_counter() - start_time
        duration_ms = duration_s * 1000

        http_requests_total.labels(
            method=method,
            path=norm_path,
            status_code=str(response.status_code),
        ).inc()
        http_request_duration_seconds.labels(method=method, path=norm_path).observe(duration_s)

        if response.status_code == 401:
            auth_failures_total.labels(path=norm_path).inc()

        log_request_end(
            request=request,
            response=response,
            request_id=request_id,
            tenant_id=tenant_id,
            user_id=user_id,
            duration_ms=duration_ms,
        )

        response.headers["X-Request-ID"] = request_id
        return response

    @staticmethod
    def _extract_or_generate_request_id(request: Request) -> str:
        """Extract X-Request-ID header or generate a new UUID."""
        request_id = request.headers.get("X-Request-ID")
        if request_id:
            return request_id
        return str(uuid.uuid4())

    @staticmethod
    def _extract_user_id_from_jwt(request: Request) -> str | None:
        """Extract user_id from JWT token if present.

        JWT format: Bearer <token>.
        Decode only the payload (base64, no signature validation here).
        """
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        try:
            import base64
            import json

            token = auth_header[7:]
            parts = token.split(".")
            if len(parts) != 3:
                return None

            payload = parts[1]
            padding = 4 - (len(payload) % 4)
            if padding != 4:
                payload += "=" * padding

            decoded = base64.urlsafe_b64decode(payload)
            claims = json.loads(decoded)
            return claims.get("sub")
        except Exception:
            return None


def log_request_start(
    request: Request,
    request_id: str,
    tenant_id: str | None,
    user_id: str | None,
) -> None:
    """Log incoming request with method, path, query params, headers."""
    query_params = dict(request.query_params) if request.query_params else {}
    query_params_masked = mask_sensitive_fields(query_params)

    logger.info(
        f"{request.method} {request.url.path}",
        extra={
            "event": "request_start",
            "request_id": request_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "method": request.method,
            "path": request.url.path,
            "query_params": query_params_masked,
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        },
    )


def log_request_end(
    request: Request,
    response: Response,
    request_id: str,
    tenant_id: str | None,
    user_id: str | None,
    duration_ms: float,
) -> None:
    """Log response with status code and duration."""
    response_size = response.headers.get("content-length", "unknown")

    log_level = "warning" if response.status_code >= 400 else "info"
    log_fn = getattr(logger, log_level)

    log_fn(
        f"{request.method} {request.url.path} {response.status_code} {duration_ms:.1f}ms",
        extra={
            "event": "request_end",
            "request_id": request_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 1),
            "response_size_bytes": response_size,
        },
    )
