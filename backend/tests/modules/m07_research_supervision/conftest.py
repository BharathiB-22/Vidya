"""
Local conftest for M07 unit tests.

All tests in this directory are pure unit tests (mocks/source inspection only).
Override the session-scoped autouse DB fixture from the root conftest so that
Alembic migrations are not required to run these tests.
"""
import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_public_schema():
    """No-op override: M07 unit tests do not require a live database."""
    pass
