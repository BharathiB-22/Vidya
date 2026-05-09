import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_public_schema():
    """No-op override: pure-Python unit tests need no DB connection."""
    pass
