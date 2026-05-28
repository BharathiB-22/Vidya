"""
Regression tests — M03 Celery workers must use NullPool.

Guards against re-introducing the "Future attached to a different loop" bug
on Windows --pool=solo, where each asyncio.run() creates a new event loop
and pooled asyncpg connections from the previous loop become invalid.
Applies to both the generation and export workers.
"""
from __future__ import annotations


def _assert_null_pool(mod, monkeypatch):
    """Helper: reset cached engine, create fresh one, assert NullPool."""
    from sqlalchemy.pool import NullPool

    original = mod._async_engine
    mod._async_engine = None

    class _FakeSettings:
        DATABASE_URL = "postgresql+asyncpg://x:x@localhost/x"

    monkeypatch.setattr("app.config.settings", _FakeSettings())

    try:
        engine = mod._get_async_engine()
        assert isinstance(engine.pool, NullPool), (
            f"Expected NullPool, got {type(engine.pool).__name__}. "
            "Using a pooling engine on Windows --pool=solo causes "
            "'Future attached to a different loop' on the second task invocation."
        )
    finally:
        mod._async_engine = original


def test_generation_engine_uses_null_pool(monkeypatch):
    """course_kit_generation._get_async_engine() must use NullPool."""
    import app.workers.heavy.course_kit_generation as mod
    _assert_null_pool(mod, monkeypatch)


def test_export_engine_uses_null_pool(monkeypatch):
    """course_kit_export._get_async_engine() must use NullPool."""
    import app.workers.heavy.course_kit_export as mod
    _assert_null_pool(mod, monkeypatch)


