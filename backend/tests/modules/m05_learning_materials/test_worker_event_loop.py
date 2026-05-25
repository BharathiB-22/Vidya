"""
Regression test: M05 Celery workers must use NullPool so that asyncpg
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
# curate_learning_package
# ---------------------------------------------------------------------------

def test_curate_learning_package_engine_uses_nullpool():
    """_get_async_engine() in curate_learning_package must use NullPool."""
    from sqlalchemy.pool import NullPool

    captured = {}

    def fake_create_engine(url, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    with patch("sqlalchemy.ext.asyncio.create_async_engine", fake_create_engine):
        import app.workers.heavy.curate_learning_package as mod
        mod._async_engine = None
        mod._get_async_engine()

    assert captured.get("poolclass") is NullPool, (
        "curate_learning_package._get_async_engine() must pass poolclass=NullPool "
        "to prevent cross-event-loop connection reuse on Windows --pool=solo."
    )


# ---------------------------------------------------------------------------
# index_package_rag
# ---------------------------------------------------------------------------

def test_index_package_rag_engine_uses_nullpool():
    """_get_async_engine() in index_package_rag must use NullPool."""
    from sqlalchemy.pool import NullPool

    captured = {}

    def fake_create_engine(url, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    with patch("sqlalchemy.ext.asyncio.create_async_engine", fake_create_engine):
        import app.workers.heavy.index_package_rag as mod
        mod._async_engine = None
        mod._get_async_engine()

    assert captured.get("poolclass") is NullPool, (
        "index_package_rag._get_async_engine() must pass poolclass=NullPool "
        "to prevent cross-event-loop connection reuse on Windows --pool=solo."
    )


# ---------------------------------------------------------------------------
# Regression: AuditLog FK to public.tenants must resolve in worker context
# ---------------------------------------------------------------------------

def test_audit_log_model_import_registers_public_tenants():
    """Importing AuditLog must also register public.tenants in Base.metadata.

    In Celery worker processes the FastAPI app is never loaded, so
    app.core.auth.models (which defines Tenant → public.tenants) is not
    imported via routers.  Without the side-effect import in audit_log/models.py,
    configure_mappers() raises NoReferencedTableError when the worker calls
    AuditService.log() — even though the exception is swallowed, the audit row
    is never written.

    Regression for: audit_write_failed NoReferencedTableError in M05 workers.
    """
    from app.core.audit_log.models import AuditLog  # noqa: F401
    from app.database import Base

    table_keys = {
        (t.schema, t.name) for t in Base.metadata.tables.values()
    }
    assert ("public", "tenants") in table_keys, (
        "public.tenants is not in Base.metadata after importing AuditLog. "
        "The side-effect import in audit_log/models.py may have been removed."
    )
