import pytest


# The session-scoped setup_public_schema fixture in tests/conftest.py tries to
# run Alembic via subprocess, which requires a live database.  Unit tests in
# this directory use import + assert only — no DB.  This override prevents the
# autouse fixture from blocking pure unit test runs.
@pytest.fixture(scope="session", autouse=True)
def setup_public_schema():
    pass
