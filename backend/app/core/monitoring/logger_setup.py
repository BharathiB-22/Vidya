import contextvars
import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
tenant_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "tenant_id", default=None
)
user_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "user_id", default=None
)


PII_PATTERNS = {
    "password": {"mask_type": "full"},
    "passwd": {"mask_type": "full"},
    "token": {"mask_type": "full"},
    "jwt": {"mask_type": "full"},
    "refresh_token": {"mask_type": "full"},
    "access_token": {"mask_type": "full"},
    "api_key": {"mask_type": "full"},
    "secret": {"mask_type": "full"},
    "secret_key": {"mask_type": "full"},
    "api_secret": {"mask_type": "full"},
    "key": {"mask_type": "full"},
    "email": {"mask_type": "email"},
    "phone": {"mask_type": "phone"},
    "mobile": {"mask_type": "phone"},
    "ssn": {"mask_type": "full"},
    "credit_card": {"mask_type": "full"},
    "authorization": {"mask_type": "full"},
}


def mask_sensitive_fields(obj: Any) -> Any:
    """Recursively mask sensitive fields in dicts, lists, and strings.

    Returns a sanitized copy without modifying the input.
    """
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            key_lower = key.lower()
            if any(pattern in key_lower for pattern in PII_PATTERNS.keys()):
                result[key] = _apply_mask(key_lower, value)
            else:
                result[key] = mask_sensitive_fields(value)
        return result
    elif isinstance(obj, list):
        return [mask_sensitive_fields(item) for item in obj]
    elif isinstance(obj, str):
        return obj
    else:
        return obj


def _apply_mask(field_name: str, value: Any) -> str:
    """Apply mask rule to a value based on field name and mask type."""
    if not isinstance(value, str):
        return "***MASKED***"

    if not value:
        return value

    for pattern_key, rule in PII_PATTERNS.items():
        if pattern_key in field_name:
            mask_type = rule.get("mask_type", "full")

            if mask_type == "full":
                return "***MASKED***"
            elif mask_type == "email":
                return _mask_email(value)
            elif mask_type == "phone":
                return _mask_phone(value)

    return "***MASKED***"


def _mask_email(email: str) -> str:
    """Mask email leaving domain visible: user@example.com -> u***@example.com."""
    try:
        if "@" not in email:
            return "***MASKED***"
        local, domain = email.split("@", 1)
        if len(local) <= 1:
            return f"u***@{domain}"
        return f"{local[0]}***@{domain}"
    except Exception:
        return "***MASKED***"


def _mask_phone(phone: str) -> str:
    """Mask phone leaving last 4 digits: +1-555-123-4567 -> ***-***-4567."""
    try:
        digits = re.sub(r"\D", "", phone)
        if len(digits) < 4:
            return "***MASKED***"
        return f"***-***-{digits[-4:]}"
    except Exception:
        return "***MASKED***"


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON with PII masking."""

    def format(self, record: logging.LogRecord) -> str:
        """Convert LogRecord to JSON line."""
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()

        log_obj = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
            "tenant_id": tenant_id_ctx.get(),
            "user_id": user_id_ctx.get(),
            "module": record.module,
            "line": record.lineno,
        }

        if record.exc_info and record.exc_text:
            log_obj["exception"] = record.exc_text

        extra_fields = getattr(record, "extra_fields", None)
        if extra_fields:
            log_obj["extra"] = mask_sensitive_fields(extra_fields)

        try:
            return json.dumps(log_obj, default=str)
        except Exception as e:
            log_obj["serialization_error"] = str(e)
            return json.dumps(log_obj, default=str)


class LogRecordWithExtra(logging.LogRecord):
    """Extended LogRecord that supports extra_fields attribute."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_fields = {}


def setup_logging(log_level: str = "INFO", json_logging: bool = True) -> None:
    """Initialize structured logging for Vidya.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_logging: If True, use JSON formatter; else use standard format
    """
    if json_logging:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
    else:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
        handler.setFormatter(formatter)

    logging.setLogRecordFactory(LogRecordWithExtra)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    logging.getLogger("vidya.access").setLevel(log_level)
    logging.getLogger("vidya.error").setLevel(log_level)
    logging.getLogger("vidya.celery").setLevel(log_level)
