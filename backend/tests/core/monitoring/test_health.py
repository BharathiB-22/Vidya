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
    """Test that check_all returns list of results for all four services."""

    async def mock_db(*args, **kwargs):
        return HealthCheckResult("db", "healthy", 10.0)

    async def mock_redis(*args, **kwargs):
        return HealthCheckResult("redis", "healthy", 5.0)

    async def mock_s3(*args, **kwargs):
        return HealthCheckResult("s3", "healthy", 8.0)

    async def mock_qdrant(*args, **kwargs):
        return HealthCheckResult("qdrant", "healthy", 3.0)

    monkeypatch.setattr(HealthService, "check_db_connection", mock_db)
    monkeypatch.setattr(HealthService, "check_redis_connection", mock_redis)
    monkeypatch.setattr(HealthService, "check_s3_connection", mock_s3)
    monkeypatch.setattr(HealthService, "check_qdrant_connection", mock_qdrant)

    results, all_healthy = await HealthService.check_all()

    assert len(results) == 4
    assert all_healthy is True
    assert any(r.service == "db" for r in results)
    assert any(r.service == "redis" for r in results)
    assert any(r.service == "s3" for r in results)
    assert any(r.service == "qdrant" for r in results)


@pytest.mark.asyncio
async def test_check_all_detects_unhealthy_service(monkeypatch):
    """Test that check_all detects when a service is unhealthy."""

    async def mock_db(*args, **kwargs):
        return HealthCheckResult("db", "unhealthy", 2000.0, "timeout")

    async def mock_redis(*args, **kwargs):
        return HealthCheckResult("redis", "healthy", 5.0)

    async def mock_s3(*args, **kwargs):
        return HealthCheckResult("s3", "healthy", 8.0)

    async def mock_qdrant(*args, **kwargs):
        return HealthCheckResult("qdrant", "healthy", 3.0)

    monkeypatch.setattr(HealthService, "check_db_connection", mock_db)
    monkeypatch.setattr(HealthService, "check_redis_connection", mock_redis)
    monkeypatch.setattr(HealthService, "check_s3_connection", mock_s3)
    monkeypatch.setattr(HealthService, "check_qdrant_connection", mock_qdrant)

    results, all_healthy = await HealthService.check_all()

    assert all_healthy is False
    assert any(r.service == "db" and r.status == "unhealthy" for r in results)


@pytest.mark.asyncio
async def test_check_qdrant_skipped_when_url_empty(monkeypatch):
    """Test that Qdrant check returns 'skipped' when QDRANT_URL is empty."""
    from app.config import settings
    monkeypatch.setattr(settings, "QDRANT_URL", "")

    result = await HealthService.check_qdrant_connection()

    assert result.service == "qdrant"
    assert result.status == "skipped"
    assert result.latency_ms == 0.0
    assert result.error_msg is None


@pytest.mark.asyncio
async def test_check_all_treats_qdrant_skipped_as_healthy(monkeypatch):
    """Test that all_healthy is True when Qdrant is skipped (empty QDRANT_URL)."""

    async def mock_db(*args, **kwargs):
        return HealthCheckResult("db", "healthy", 10.0)

    async def mock_redis(*args, **kwargs):
        return HealthCheckResult("redis", "healthy", 5.0)

    async def mock_s3(*args, **kwargs):
        return HealthCheckResult("s3", "healthy", 8.0)

    async def mock_qdrant(*args, **kwargs):
        return HealthCheckResult("qdrant", "skipped", 0.0)

    monkeypatch.setattr(HealthService, "check_db_connection", mock_db)
    monkeypatch.setattr(HealthService, "check_redis_connection", mock_redis)
    monkeypatch.setattr(HealthService, "check_s3_connection", mock_s3)
    monkeypatch.setattr(HealthService, "check_qdrant_connection", mock_qdrant)

    results, all_healthy = await HealthService.check_all()

    assert all_healthy is True
    assert any(r.service == "qdrant" and r.status == "skipped" for r in results)


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

    def test_metrics_endpoint_returns_prometheus_format(self):
        """Test /metrics endpoint returns Prometheus text exposition format."""
        client = TestClient(app)
        response = client.get("/metrics")

        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")
        assert "vidya_" in response.text

    def test_liveness_endpoint_response_format(self):
        """Test /healthz response format is valid."""
        client = TestClient(app)
        response = client.get("/healthz")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["status"], str)
        assert isinstance(data["environment"], str)
        assert "T" in data["timestamp"]
