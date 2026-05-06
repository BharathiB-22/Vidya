import pytest


# The session-scoped setup_public_schema fixture in tests/conftest.py attempts
# to run Alembic via subprocess, which requires a live database. Unit tests in
# this directory use mocks and need no database. This no-op override prevents
# the autouse fixture from blocking pure unit test runs.
@pytest.fixture(scope="session", autouse=True)
def setup_public_schema():
    pass
