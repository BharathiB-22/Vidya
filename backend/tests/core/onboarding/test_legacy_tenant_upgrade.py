"""Legacy-tenant upgrade — regression for ``usn_sequence_counters`` missing on
tenants created before migration 0050ten.

Reproduces the production failure where Student Import raised
``relation "usn_sequence_counters" does not exist`` for a tenant (e.g. LMS
University) provisioned before the USN auto-generation feature shipped, and
proves that ``app.management.upgrade_all_tenants`` forward-migrates such a legacy
schema to head automatically — the same path the Helm migrate-job now runs on
every deploy — so no manual DB intervention is required.

Integration: requires a live PostgreSQL (same contract as the other onboarding
integration tests). The session-scoped ``setup_public_schema`` autouse fixture
(tests/conftest.py) brings the public schema to head, which ``upgrade_all_tenants``
reads to discover tenants.

The test is synchronous on purpose: ``upgrade_all_tenants`` drives Alembic through
its own *synchronous* engine, and Alembic's tenant ``env.py`` calls
``asyncio.run(...)`` internally. Invoking it from inside a running event loop
(an async test) would raise "asyncio.run() cannot be called from a running event
loop" — the provisioner sidesteps this with ``asyncio.to_thread``; here a plain
sync test has no running loop at all.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text

from app.config import settings
from app.management import upgrade_all_tenants

_BACKEND_DIR = str(Path(__file__).resolve().parents[3])

_LEGACY_SCHEMA = "tenant_legacy_usn_test"
_LEGACY_SLUG = "legacy-usn-test"
# Last tenant revision before usn_sequence_counters was introduced (0050ten).
_PRE_USN_REV = "0049ten"

_sync_engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)


def _alembic_upgrade_to(rev: str, schema: str) -> None:
    """Run the tenant Alembic track up to a specific revision for one schema."""
    env = {**os.environ, "ALEMBIC_TARGET": "tenant", "TENANT_SCHEMA": schema}
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", rev],
        cwd=_BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"alembic upgrade {rev} failed:\n{proc.stderr}"


def _table_exists(schema: str, table: str) -> bool:
    with _sync_engine.connect() as c:
        return c.execute(
            text("SELECT to_regclass(:t)"), {"t": f"{schema}.{table}"}
        ).scalar() is not None


def _alembic_version(schema: str) -> str | None:
    with _sync_engine.connect() as c:
        return c.execute(
            text(f"SELECT version_num FROM {schema}.alembic_version")
        ).scalar_one_or_none()


def _register_active_tenant(schema: str, slug: str) -> None:
    with _sync_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO public.tenants "
                "    (id, slug, name, schema_name, is_active, status) "
                "VALUES (:id, :slug, :name, :schema, true, 'ACTIVE') "
                "ON CONFLICT (slug) DO UPDATE SET is_active = true, "
                "    status = 'ACTIVE', schema_name = EXCLUDED.schema_name"
            ),
            {"id": str(uuid.uuid4()), "slug": slug, "name": "Legacy USN Test", "schema": schema},
        )


def _cleanup(schema: str, slug: str) -> None:
    with _sync_engine.begin() as c:
        # Archive (not delete) the tenant row — audit_logs.tenant_id has an
        # ON DELETE SET NULL FK that the append-only trigger would block; setting
        # status away from ACTIVE also keeps the row out of upgrade_all_tenants.
        c.execute(
            text("UPDATE public.tenants SET is_active = false, status = 'ARCHIVED' "
                 "WHERE slug = :slug"),
            {"slug": slug},
        )
        c.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))


def test_upgrade_all_tenants_forward_migrates_legacy_schema(setup_public_schema):
    """A tenant pinned below 0050ten gains usn_sequence_counters via the script."""
    with _sync_engine.begin() as c:
        c.execute(text(f"DROP SCHEMA IF EXISTS {_LEGACY_SCHEMA} CASCADE"))

    try:
        # 1. Simulate a legacy tenant: migrated only up to the pre-USN revision.
        _alembic_upgrade_to(_PRE_USN_REV, _LEGACY_SCHEMA)
        _register_active_tenant(_LEGACY_SCHEMA, _LEGACY_SLUG)

        # Precondition: reproduces the production failure mode exactly.
        assert _alembic_version(_LEGACY_SCHEMA) == _PRE_USN_REV
        assert not _table_exists(_LEGACY_SCHEMA, "usn_sequence_counters"), (
            "precondition broken — legacy schema should NOT have the USN table yet"
        )

        # 2. Run the deploy-time upgrade for just this schema.
        rc = upgrade_all_tenants.main(["--schema", _LEGACY_SCHEMA])
        assert rc == 0

        # 3. The table now exists and the schema advanced past the pre-USN rev.
        assert _table_exists(_LEGACY_SCHEMA, "usn_sequence_counters"), (
            "upgrade_all_tenants did not create usn_sequence_counters on the legacy schema"
        )
        assert _alembic_version(_LEGACY_SCHEMA) != _PRE_USN_REV

        # 4. Idempotent: a second run is a clean no-op (already at head).
        assert upgrade_all_tenants.main(["--schema", _LEGACY_SCHEMA]) == 0
    finally:
        _cleanup(_LEGACY_SCHEMA, _LEGACY_SLUG)
