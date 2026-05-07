import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.monitoring.health import HealthService, HealthCheckResult
from app.main import app


@pytest.mark.asyncio
async def test_health_check_result_to_dict():
    """Test HealthCheckResult serialization."""
    result = HealthCheckResult("db", "healthy", 12.5)
    d = result.to_dict()

    assert d["service"] == "db"
    assert d["status"] == "healthy"
    assert d["latency_ms"] == 12.5
    assert d["error_msg"] is None


@pytest.mark.asyncio
async def test_health_check_result_with_error():
    """Test HealthCheckResult with error message."""
    result = HealthCheckResult(
        "redis", "unhealthy", 2000.0, error_msg="Connection timeout"
    )
    d = result.to_dict()

    assert d["service"] == "redis"
    assert d["status"] == "unhealthy"
    assert d["error_msg"] == "Connection timeout"


@pytest.mark.asyncio
async def test_check_db_connection_timeout(monkeypatch):
    """Test database health check with timeout."""

    async def mock_execute(*args, **kwargs):
        await asyncio.sleep(10)

    from app.database import AsyncSessionLocal

    monkeypatch.setattr(AsyncSessionLocal(), "execute", mock_execute)

    result = await HealthService.check_db_connection(timeout=0.1)

    assert result.service == "db"
    assert result.status == "unhealthy"
    assert "timeout" in result.error_msg.lower() or result.latency_ms > 100


@pytest.mark.asyncio
async def test_check_all_returns_list(monkeypatch):
    """Test that check_all returns list of results."""

    def mock_db(*args, **kwargs):
        return HealthCheckResult("db", "healthy", 10.0)

    def mock_redis(*args, **kwargs):
        return HealthCheckResult("redis", "healthy", 5.0)

    def mock_s3(*args, **kwargs):
        return HealthCheckResult("s3", "healthy", 8.0)

    monkeypatch.setattr(HealthService, "check_db_connection", mock_db)
    monkeypatch.setattr(HealthService, "check_redis_connection", mock_redis)
    monkeypatch.setattr(HealthService, "check_s3_connection", mock_s3)

    results, all_healthy = await HealthService.check_all()

    assert len(results) == 3
    assert all_healthy is True
    assert any(r.service == "db" for r in results)
    assert any(r.service == "redis" for r in results)
    assert any(r.service == "s3" for r in results)


@pytest.mark.asyncio
async def test_check_all_detects_unhealthy_service(monkeypatch):
    """Test that check_all detects when a service is unhealthy."""

    def mock_db(*args, **kwargs):
        return HealthCheckResult("db", "unhealthy", 2000.0, "timeout")

    def mock_redis(*args, **kwargs):
        return HealthCheckResult("redis", "healthy", 5.0)

    def mock_s3(*args, **kwargs):
        return HealthCheckResult("s3", "healthy", 8.0)

    monkeypatch.setattr(HealthService, "check_db_connection", mock_db)
    monkeypatch.setattr(HealthService, "check_redis_connection", mock_redis)
    monkeypatch.setattr(HealthService, "check_s3_connection", mock_s3)

    results, all_healthy = await HealthService.check_all()

    assert all_healthy is False
    assert any(r.service == "db" and r.status == "unhealthy" for r in results)


class TestHealthEndpoints:
    """Test health check HTTP endpoints."""

    def test_liveness_endpoint_always_200(self):
        """Test /healthz endpoint always returns 200."""
        client = TestClient(app)
        response = client.get("/healthz")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert "environment" in data

    def test_readiness_endpoint_has_required_fields(self):
        """Test /ready endpoint returns required fields."""
        client = TestClient(app)
        response = client.get("/ready")

        assert response.status_code in [200, 503]
        data = response.json()
        assert "ready" in data
        assert "timestamp" in data
        assert "checks" in data
        assert isinstance(data["checks"], dict)

    def test_metrics_endpoint_has_required_fields(self):
        """Test /metrics endpoint returns required fields."""
        client = TestClient(app)
        response = client.get("/metrics")

        assert response.status_code == 200
        data = response.json()
        assert "request_count" in data
        assert "request_latency_p50_ms" in data
        assert "request_latency_p95_ms" in data
        assert "request_latency_p99_ms" in data
        assert "task_queue_depth" in data
        assert "db_connection_pool_size" in data
        assert "timestamp" in data

    def test_liveness_endpoint_response_format(self):
        """Test /healthz response format is valid."""
        client = TestClient(app)
        response = client.get("/healthz")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["status"], str)
        assert isinstance(data["environment"], str)
        assert "T" in data["timestamp"]
