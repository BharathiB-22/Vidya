"""
Regression test: M02 Celery workers must use NullPool so that asyncpg
connections are never cached across asyncio.run() calls.

On Windows with --pool=solo, each task runs under a fresh asyncio.run()
event loop.  A pooled asyncpg connection is attached to the loop that
created it; when that loop closes, reusing the connection in the next
asyncio.run() raises "Future attached to a different loop".  NullPool
prevents this by never caching connections between sessions.
"""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _fresh_module(module_path: str):
    """Import a module with a clean sys.modules entry so global state is reset."""
    if module_path in sys.modules:
        del sys.modules[module_path]
    return importlib.import_module(module_path)


# ---------------------------------------------------------------------------
# syllabus_generation
# ---------------------------------------------------------------------------

def test_syllabus_generation_engine_uses_nullpool():
    """_get_async_engine() in syllabus_generation must use NullPool."""
    from sqlalchemy.pool import NullPool

    captured = {}

    def fake_create_engine(url, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    with patch("sqlalchemy.ext.asyncio.create_async_engine", fake_create_engine):
        # Reset module-level cache before test
        import app.workers.heavy.syllabus_generation as mod
        mod._async_engine = None
        mod._get_async_engine()

    assert captured.get("poolclass") is NullPool, (
        "syllabus_generation._get_async_engine() must pass poolclass=NullPool "
        "to prevent cross-event-loop connection reuse."
    )


def test_syllabus_generation_task_does_not_set_event_loop_policy():
    """generate_syllabus task must not call asyncio.set_event_loop_policy()."""
    import ast
    import inspect
    import app.workers.heavy.syllabus_generation as mod

    source = inspect.getsource(mod.generate_syllabus)
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "set_event_loop_policy":
                raise AssertionError(
                    "generate_syllabus must not call asyncio.set_event_loop_policy(). "
                    "Changing the global loop policy mid-process causes asyncpg pool "
                    "futures to attach to the wrong loop."
                )


# ---------------------------------------------------------------------------
# reference_enrichment
# ---------------------------------------------------------------------------

def test_reference_enrichment_engine_uses_nullpool():
    """_get_async_engine() in reference_enrichment must use NullPool."""
    from sqlalchemy.pool import NullPool

    captured = {}

    def fake_create_engine(url, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    with patch("sqlalchemy.ext.asyncio.create_async_engine", fake_create_engine):
        import app.workers.heavy.reference_enrichment as mod
        mod._async_engine = None
        mod._get_async_engine()

    assert captured.get("poolclass") is NullPool, (
        "reference_enrichment._get_async_engine() must pass poolclass=NullPool."
    )
