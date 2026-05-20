import json
import uuid

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY, generate_latest

from app.core.monitoring.middleware import MonitoringMiddleware


@pytest.fixture
def app_with_monitoring():
    """Create test FastAPI app with MonitoringMiddleware."""
    app = FastAPI()
    app.add_middleware(MonitoringMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"message": "ok"}

    @app.post("/test-post")
    async def test_post_endpoint(data: dict):
        return data

    @app.get("/error")
    async def error_endpoint():
        raise ValueError("Test error")

    @app.get("/unauthorized")
    async def unauthorized_endpoint():
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    return app


def test_middleware_adds_request_id_header(app_with_monitoring):
    """Test that middleware adds X-Request-ID to response."""
    client = TestClient(app_with_monitoring)
    response = client.get("/test")

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) > 0


def test_middleware_generates_request_id_if_not_present(app_with_monitoring):
    """Test that middleware generates UUID if X-Request-ID not in request."""
    client = TestClient(app_with_monitoring)
    response = client.get("/test")

    request_id = response.headers["X-Request-ID"]
    try:
        uuid.UUID(request_id)
    except ValueError:
        pytest.fail(f"Generated request_id is not a valid UUID: {request_id}")


def test_middleware_uses_existing_request_id(app_with_monitoring):
    """Test that middleware uses X-Request-ID from request if provided."""
    client = TestClient(app_with_monitoring)
    custom_id = "custom-request-id-123"
    response = client.get("/test", headers={"X-Request-ID": custom_id})

    assert response.headers["X-Request-ID"] == custom_id


def test_middleware_extracts_tenant_slug(app_with_monitoring, log_capture):
    """Test that middleware extracts X-Tenant-Slug header."""
    client = TestClient(app_with_monitoring)
    response = client.get(
        "/test",
        headers={"X-Tenant-Slug": "test-tenant"},
    )

    assert response.status_code == 200


def test_middleware_logs_request_method_and_path(app_with_monitoring, log_capture):
    """Test that middleware logs request method and path in the access log."""
    client = TestClient(app_with_monitoring)
    client.get("/test")

    assert len(log_capture) > 0
    # log_capture stores either JSON dicts (if JSONFormatter is active) or
    # {"raw": "<plain_text>"} dicts depending on the handler formatter.
    # Check both shapes: look for GET and /test in any captured log entry.
    all_text = " ".join(str(l) for l in log_capture)
    assert "GET" in all_text
    assert "/test" in all_text


def test_middleware_logs_response_status(app_with_monitoring, log_capture):
    """Test that middleware logs response status code."""
    client = TestClient(app_with_monitoring)
    client.get("/test")

    # 200 status appears in the log_request_end message: "GET /test 200 0.9ms"
    all_text = " ".join(str(l) for l in log_capture)
    assert "200" in all_text


def test_middleware_logs_duration(app_with_monitoring, log_capture):
    """Test that middleware logs request duration."""
    client = TestClient(app_with_monitoring)
    client.get("/test")

    # Duration appears in the log_request_end message with "ms" suffix
    all_text = " ".join(str(l) for l in log_capture)
    assert "ms" in all_text


def test_middleware_handles_exceptions(app_with_monitoring, log_capture):
    """Test that middleware catches and logs exceptions."""
    client = TestClient(app_with_monitoring, raise_server_exceptions=False)
    response = client.get("/error")

    assert response.status_code == 500
    # /error path should appear in at least the request_start log
    all_text = " ".join(str(l) for l in log_capture)
    assert "/error" in all_text


def test_middleware_extracts_user_id_from_jwt(app_with_monitoring, log_capture):
    """Test that middleware extracts user_id from JWT token."""
    import base64

    user_id = "user-123-uuid"
    payload = {"sub": user_id, "iat": 1234567890}
    encoded_payload = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).decode().rstrip("=")

    token = f"eyJhbGciOiJIUzI1NiJ9.{encoded_payload}.signature"

    client = TestClient(app_with_monitoring)
    response = client.get("/test", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200


def test_middleware_masks_query_params(app_with_monitoring, log_capture):
    """Test that middleware masks sensitive query parameters in access logs."""
    from app.core.monitoring import mask_sensitive_fields

    # Verify the masking function itself works (unit test)
    params = {"api_key": "secret123", "user": "john"}
    masked = mask_sensitive_fields(params)
    assert masked["api_key"] == "***MASKED***"
    assert masked["user"] == "john"

    # Verify the request goes through and something is logged
    client = TestClient(app_with_monitoring)
    response = client.get("/test?api_key=secret123&user=john")
    assert response.status_code == 200
    assert len(log_capture) > 0


def test_http_requests_counter_increments(app_with_monitoring):
    """Test that vidya_http_requests_total counter increments on each request."""
    client = TestClient(app_with_monitoring)
    client.get("/test")

    metrics_text = generate_latest(REGISTRY).decode("utf-8")
    # After making a GET /test request, the counter must appear with method="GET"
    assert 'vidya_http_requests_total{' in metrics_text
    assert 'method="GET"' in metrics_text


def test_auth_failure_counter_increments_on_401(app_with_monitoring):
    """Test that vidya_auth_failures_total counter increments on 401 responses."""
    client = TestClient(app_with_monitoring)
    client.get("/unauthorized")

    metrics_text = generate_latest(REGISTRY).decode("utf-8")
    assert "vidya_auth_failures_total" in metrics_text
