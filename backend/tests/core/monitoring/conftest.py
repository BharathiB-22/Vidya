import json
import logging

import pytest


@pytest.fixture
def log_capture():
    """Capture JSON logs to a list for inspection."""
    logs = []

    class LogCapture(logging.Handler):
        def emit(self, record):
            try:
                msg = self.format(record)
                if msg.startswith("{"):
                    logs.append(json.loads(msg))
                else:
                    logs.append({"raw": msg})
            except Exception:
                pass

    handler = LogCapture()
    logger = logging.getLogger("vidya.access")
    logger.addHandler(handler)

    yield logs

    logger.removeHandler(handler)


@pytest.fixture
def mock_redis_unavailable(monkeypatch):
    """Mock Redis to be unavailable for health check tests."""
    import socket

    def mock_connect(self, address):
        raise ConnectionRefusedError("Redis unavailable")

    monkeypatch.setattr(socket.socket, "connect", mock_connect)
