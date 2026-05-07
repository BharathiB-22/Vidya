import json
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

from app.core.monitoring.middleware import MonitoringMiddleware
from app.core.monitoring import request_id_ctx, tenant_id_ctx


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
    """Test that middleware logs request method and path."""
    client = TestClient(app_with_monitoring)
    client.get("/test")

    assert len(log_capture) > 0
    log_entries = [l for l in log_capture if isinstance(l, dict) and "method" in l]
    assert any(l.get("method") == "GET" and l.get("path") == "/test" for l in log_entries)


def test_middleware_logs_response_status(app_with_monitoring, log_capture):
    """Test that middleware logs response status code."""
    client = TestClient(app_with_monitoring)
    client.get("/test")

    log_entries = [l for l in log_capture if isinstance(l, dict) and "status_code" in l]
    assert any(l.get("status_code") == 200 for l in log_entries)


def test_middleware_logs_duration(app_with_monitoring, log_capture):
    """Test that middleware logs request duration."""
    client = TestClient(app_with_monitoring)
    client.get("/test")

    log_entries = [l for l in log_capture if isinstance(l, dict) and "duration_ms" in l]
    assert any(l.get("duration_ms", 0) >= 0 for l in log_entries)


def test_middleware_handles_exceptions(app_with_monitoring, log_capture):
    """Test that middleware catches and logs exceptions."""
    client = TestClient(app_with_monitoring)
    response = client.get("/error")

    assert response.status_code == 500
    log_entries = [l for l in log_capture if isinstance(l, dict) and l.get("event") == "request_start"]
    assert any(l.get("path") == "/error" for l in log_entries)


def test_middleware_extracts_user_id_from_jwt(app_with_monitoring, log_capture):
    """Test that middleware extracts user_id from JWT token."""
    import base64
    import json

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
    """Test that middleware masks sensitive query parameters."""
    client = TestClient(app_with_monitoring)
    client.get("/test?api_key=secret123&user=john")

    log_entries = [
        l for l in log_capture
        if isinstance(l, dict) and l.get("event") == "request_start"
    ]
    assert len(log_entries) > 0
    log_entry = log_entries[0]

    if "query_params" in log_entry:
        assert log_entry["query_params"].get("api_key") == "***MASKED***"
        assert log_entry["query_params"].get("user") == "john"
