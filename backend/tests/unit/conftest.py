"""
Local conftest for pure unit tests that require no database.

Overrides the session-scoped setup_public_schema fixture from the parent
conftest so Alembic is never called when running tests in this directory.
"""
import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_public_schema():
    """No-op override — unit tests have no DB dependency."""
