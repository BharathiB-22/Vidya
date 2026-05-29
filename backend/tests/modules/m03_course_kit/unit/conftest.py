"""
Unit-level conftest: overrides the root session fixture so pure-Python
unit tests run without a live database connection.
"""
import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_public_schema():
    """No-op: unit tests are pure Python — no DB needed."""
    pass
