"""
M10 unit test conftest — overrides the root DB autouse fixture.
All M10 tests in this directory are pure-function tests (no real DB needed).
"""
import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_public_schema():
    """No-op override — M10 unit tests mock all DB calls."""
    pass
