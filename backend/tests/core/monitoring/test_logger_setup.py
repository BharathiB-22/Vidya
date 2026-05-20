import json
import logging

from app.core.monitoring.logger_setup import (
    JSONFormatter,
    mask_sensitive_fields,
    request_id_ctx,
    tenant_id_ctx,
    user_id_ctx,
)


class TestPIIMasking:
    """Test PII field masking."""

    def test_mask_password_field(self):
        obj = {"password": "secret123", "user": "john"}
        result = mask_sensitive_fields(obj)
        assert result["password"] == "***MASKED***"
        assert result["user"] == "john"

    def test_mask_token_field(self):
        obj = {"token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", "status": "ok"}
        result = mask_sensitive_fields(obj)
        assert result["token"] == "***MASKED***"
        assert result["status"] == "ok"

    def test_mask_jwt_field(self):
        obj = {"jwt": "very.long.token", "id": 123}
        result = mask_sensitive_fields(obj)
        assert result["jwt"] == "***MASKED***"

    def test_mask_api_key_field(self):
        obj = {"api_key": "sk-12345abcde", "version": "v1"}
        result = mask_sensitive_fields(obj)
        assert result["api_key"] == "***MASKED***"

    def test_mask_secret_field(self):
        obj = {"secret": "mysecret", "name": "app"}
        result = mask_sensitive_fields(obj)
        assert result["secret"] == "***MASKED***"

    def test_mask_email_field(self):
        obj = {"email": "john.doe@example.com"}
        result = mask_sensitive_fields(obj)
        assert "@" in result["email"]
        assert "john.doe" not in result["email"]
        assert "example.com" in result["email"]

    def test_mask_phone_field(self):
        obj = {"phone": "+1-555-123-4567"}
        result = mask_sensitive_fields(obj)
        assert "4567" in result["phone"]
        assert "555" not in result["phone"]

    def test_mask_recursive_in_dict(self):
        obj = {
            "user": {"password": "secret", "email": "john@example.com"},
            "status": "ok",
        }
        result = mask_sensitive_fields(obj)
        assert result["user"]["password"] == "***MASKED***"
        assert "@" in result["user"]["email"]
        assert result["status"] == "ok"

    def test_mask_recursive_in_list(self):
        obj = [
            {"password": "secret1"},
            {"password": "secret2"},
            {"status": "ok"},
        ]
        result = mask_sensitive_fields(obj)
        assert result[0]["password"] == "***MASKED***"
        assert result[1]["password"] == "***MASKED***"
        assert result[2]["status"] == "ok"

    def test_no_mask_for_safe_fields(self):
        obj = {
            "user_id": "uuid-here",
            "tenant_id": "uuid-here",
            "name": "John Doe",
        }
        result = mask_sensitive_fields(obj)
        assert result["user_id"] == "uuid-here"
        assert result["tenant_id"] == "uuid-here"
        assert result["name"] == "John Doe"


class TestJSONFormatter:
    """Test JSON log formatting."""

    def test_formatter_outputs_valid_json(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="vidya.access",
            level=logging.INFO,
            pathname="main.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        parsed = json.loads(result)
        assert parsed["logger"] == "vidya.access"
        assert parsed["message"] == "Test message"
        assert parsed["level"] == "INFO"
        assert "timestamp" in parsed

    def test_formatter_includes_context_vars(self):
        request_id_ctx.set("req-123")
        tenant_id_ctx.set("tenant-456")
        user_id_ctx.set("user-789")

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="vidya.access",
            level=logging.INFO,
            pathname="main.py",
            lineno=42,
            msg="Test with context",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        parsed = json.loads(result)

        assert parsed["request_id"] == "req-123"
        assert parsed["tenant_id"] == "tenant-456"
        assert parsed["user_id"] == "user-789"

        request_id_ctx.set(None)
        tenant_id_ctx.set(None)
        user_id_ctx.set(None)

    def test_formatter_single_line_output(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="vidya.access",
            level=logging.INFO,
            pathname="main.py",
            lineno=42,
            msg="Test\nmultiline\nmessage",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert "\n" not in result
        assert result.startswith("{")
        assert result.endswith("}")

    def test_formatter_masks_sensitive_in_extra_fields(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="vidya.access",
            level=logging.INFO,
            pathname="main.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.extra_fields = {
            "api_key": "secret-key",
            "user_id": "safe-user-id",
        }
        result = formatter.format(record)
        parsed = json.loads(result)

        assert parsed["extra"]["api_key"] == "***MASKED***"
        assert parsed["extra"]["user_id"] == "safe-user-id"


class TestContextVars:
    """Test context variable behavior."""

    def test_context_var_isolation(self):
        request_id_ctx.set("req-1")
        assert request_id_ctx.get() == "req-1"

        request_id_ctx.set("req-2")
        assert request_id_ctx.get() == "req-2"

        request_id_ctx.set(None)
        assert request_id_ctx.get() is None

    def test_multiple_context_vars(self):
        request_id_ctx.set("req-123")
        tenant_id_ctx.set("tenant-456")
        user_id_ctx.set("user-789")

        assert request_id_ctx.get() == "req-123"
        assert tenant_id_ctx.get() == "tenant-456"
        assert user_id_ctx.get() == "user-789"

        request_id_ctx.set(None)
        tenant_id_ctx.set(None)
        user_id_ctx.set(None)
