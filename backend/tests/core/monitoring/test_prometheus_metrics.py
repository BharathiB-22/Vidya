from fastapi.testclient import TestClient

from app.main import app
from app.core.monitoring.prometheus_metrics import normalize_path


class TestMetricsEndpoint:
    def test_metrics_endpoint_returns_200(self):
        client = TestClient(app)
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_endpoint_content_type_is_text_plain(self):
        client = TestClient(app)
        response = client.get("/metrics")
        assert "text/plain" in response.headers.get("content-type", "")

    def test_metrics_endpoint_contains_vidya_prefix(self):
        client = TestClient(app)
        # Trigger at least one request so counters have samples
        client.get("/healthz")
        response = client.get("/metrics")
        assert "vidya_" in response.text

    def test_metrics_endpoint_contains_http_counter(self):
        client = TestClient(app)
        client.get("/healthz")  # ensure counter has at least one sample
        response = client.get("/metrics")
        assert "vidya_http_requests_total" in response.text

    def test_metrics_endpoint_contains_python_metrics(self):
        """Default prometheus_client Python GC metrics are present (all platforms)."""
        client = TestClient(app)
        response = client.get("/metrics")
        # python_info is from the default platform collector available on all platforms
        assert "python_info" in response.text

    def test_metrics_endpoint_not_json(self):
        """Prometheus text format must not be JSON (no leading brace)."""
        client = TestClient(app)
        response = client.get("/metrics")
        assert not response.text.strip().startswith("{")


class TestNormalizePath:
    def test_strips_uuid(self):
        path = "/api/v1/tenants/550e8400-e29b-41d4-a716-446655440000/users"
        result = normalize_path(path)
        assert "550e8400" not in result
        assert "{id}" in result

    def test_strips_integer_id_at_end(self):
        path = "/api/v1/submissions/12345"
        result = normalize_path(path)
        assert "12345" not in result
        assert result == "/api/v1/submissions/{id}"

    def test_strips_integer_id_in_middle(self):
        path = "/api/v1/users/99/assignments"
        result = normalize_path(path)
        assert "99" not in result
        assert result == "/api/v1/users/{id}/assignments"

    def test_preserves_named_segments(self):
        path = "/api/v1/tenants/list"
        result = normalize_path(path)
        assert result == "/api/v1/tenants/list"

    def test_preserves_version_segments(self):
        path = "/api/v1/health"
        result = normalize_path(path)
        assert result == "/api/v1/health"

    def test_strips_multiple_integer_ids(self):
        path = "/tenants/42/users/99"
        result = normalize_path(path)
        assert "42" not in result
        assert "99" not in result
        assert result == "/tenants/{id}/users/{id}"

    def test_leaves_root_path_unchanged(self):
        assert normalize_path("/") == "/"

    def test_leaves_healthz_unchanged(self):
        assert normalize_path("/healthz") == "/healthz"
