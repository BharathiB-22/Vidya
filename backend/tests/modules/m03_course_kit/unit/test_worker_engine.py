"""
Regression tests — M02 + M03 Celery workers must use NullPool.

Guards against re-introducing the "Future attached to a different loop" bug
on Windows --pool=solo, where each asyncio.run() creates a new event loop
and pooled asyncpg connections from the previous loop become invalid.
Applies to syllabus generation, kit generation, and kit export workers.

Also guards that generate_syllabus sets WindowsSelectorEventLoopPolicy on
Windows — the missing policy was the primary cause of intermittent M02 failures.
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


def test_syllabus_generation_engine_uses_null_pool(monkeypatch):
    """syllabus_generation._get_async_engine() must use NullPool."""
    import app.workers.heavy.syllabus_generation as mod
    _assert_null_pool(mod, monkeypatch)


def test_generate_syllabus_sets_windows_selector_policy():
    """generate_syllabus must set WindowsSelectorEventLoopPolicy on win32.

    Missing this causes asyncpg to bind its connections to the ProactorEventLoop,
    then fail on the next asyncio.run() call with a new SelectorEventLoop.
    This was the primary cause of intermittent M02 generation failures on Windows.
    """
    import inspect
    import app.workers.heavy.syllabus_generation as mod

    src = inspect.getsource(mod.generate_syllabus)
    assert "WindowsSelectorEventLoopPolicy" in src, (
        "generate_syllabus must call asyncio.set_event_loop_policy("
        "asyncio.WindowsSelectorEventLoopPolicy()) when sys.platform == 'win32'."
    )
    assert "sys.platform" in src, (
        "generate_syllabus must guard the policy with 'if sys.platform == \"win32\"'."
    )


def test_generate_course_kit_sets_windows_selector_policy():
    """generate_course_kit must set WindowsSelectorEventLoopPolicy on win32.

    Same event-loop issue as M02: ProactorEventLoop + asyncpg fails on
    the second asyncio.run() call in a --pool=solo worker.
    """
    import inspect
    import app.workers.heavy.course_kit_generation as mod

    src = inspect.getsource(mod.generate_course_kit)
    assert "WindowsSelectorEventLoopPolicy" in src, (
        "generate_course_kit must call asyncio.set_event_loop_policy("
        "asyncio.WindowsSelectorEventLoopPolicy()) when sys.platform == 'win32'."
    )
    assert "sys.platform" in src, (
        "generate_course_kit must guard the policy with 'if sys.platform == \"win32\"'."
    )


