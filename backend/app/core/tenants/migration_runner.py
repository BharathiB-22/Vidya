"""
Automatic tenant schema migration runner.

Discovers all active tenant schemas, compares their alembic_version to the
current head, and applies any pending migrations.  Each run is logged to
public.tenant_migration_log so the System → Tenant Migrations admin page can
surface status, history, and retry options.

Design constraints:
- Failures are isolated per tenant — one failed schema never crashes startup.
- Uses the same _PROVISION_LOCK as provisioner.py to serialise alembic runs
  (alembic env.py reads ALEMBIC_TARGET / TENANT_SCHEMA from os.environ; the
  lock prevents concurrent mutation of those vars).
- get_tenant_head() caches the computed head revision for the lifetime of the
  process — the head only changes on code deployment.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text

from app.database import AsyncSessionLocal

logger = logging.getLogger("vidya.migrations")

_ALEMBIC_DIR = Path(__file__).resolve().parents[3] / "alembic"
_head_cache: str | None = None


# ---------------------------------------------------------------------------
# Head revision (cached)
# ---------------------------------------------------------------------------

def get_tenant_head() -> str:
    """Return the current head revision for tenant migrations."""
    global _head_cache
    if _head_cache is None:
        from alembic.script import ScriptDirectory
        script = ScriptDirectory(
            str(_ALEMBIC_DIR),
            version_locations=[str(_ALEMBIC_DIR / "tenant_versions")],
        )
        _head_cache = script.get_current_head() or ""
    return _head_cache


# ---------------------------------------------------------------------------
# Per-tenant helpers
# ---------------------------------------------------------------------------

async def _get_current_revision(schema_name: str) -> str | None:
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text(f"SELECT version_num FROM {schema_name}.alembic_version LIMIT 1")
            )
            return result.scalar_one_or_none()
    except Exception:
        return None


async def _write_log(
    *,
    schema_name: str,
    tenant_id: UUID | None,
    from_revision: str | None,
    to_revision: str | None,
    status: str,
    error_message: str | None = None,
) -> None:
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "INSERT INTO public.tenant_migration_log "
                    "    (id, schema_name, tenant_id, from_revision, to_revision, "
                    "     status, error_message, finished_at) "
                    "VALUES (:id, :schema, :tid, :from_rev, :to_rev, "
                    "        :status, :err, :finished_at)"
                ),
                {
                    "id": str(uuid4()),
                    "schema": schema_name,
                    "tid": str(tenant_id) if tenant_id else None,
                    "from_rev": from_revision,
                    "to_rev": to_revision,
                    "status": status,
                    "err": error_message,
                    "finished_at": datetime.now(timezone.utc),
                },
            )
            await db.commit()
    except Exception as exc:
        logger.error("Failed to write migration log for %s: %s", schema_name, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def migrate_tenant(
    schema_name: str,
    tenant_id: UUID | None = None,
) -> dict:
    """Run pending tenant migrations for a single schema.

    Returns a result dict with keys: status, schema_name, from_revision,
    to_revision, and optionally error.  Never raises.
    """
    from app.core.tenants.provisioner import _PROVISION_LOCK, _migrate_sync

    head = get_tenant_head()
    current = await _get_current_revision(schema_name)

    if current == head:
        return {
            "schema_name": schema_name,
            "status": "current",
            "from_revision": current,
            "to_revision": head,
        }

    logger.info("Migrating %s: %s → %s", schema_name, current or "new", head)
    async with _PROVISION_LOCK:
        try:
            await asyncio.to_thread(_migrate_sync, schema_name)
            await _write_log(
                schema_name=schema_name, tenant_id=tenant_id,
                from_revision=current, to_revision=head,
                status="success",
            )
            logger.info("Migration success: %s", schema_name)
            return {
                "schema_name": schema_name,
                "status": "success",
                "from_revision": current,
                "to_revision": head,
            }
        except Exception as exc:
            err = str(exc)
            logger.error("Migration failed for %s: %s", schema_name, err)
            await _write_log(
                schema_name=schema_name, tenant_id=tenant_id,
                from_revision=current, to_revision=head,
                status="failed", error_message=err,
            )
            return {
                "schema_name": schema_name,
                "status": "failed",
                "from_revision": current,
                "to_revision": head,
                "error": err,
            }


async def get_all_migration_status(db) -> list[dict]:
    """Return migration status for every non-deleted tenant.

    Used by GET /tenants/migrations.
    """
    head = get_tenant_head()

    tenants_result = await db.execute(
        text(
            "SELECT id, name, schema_name FROM public.tenants "
            "WHERE status != 'PERMANENTLY_DELETED' "
            "  AND schema_name IS NOT NULL "
            "ORDER BY name"
        )
    )
    tenants = tenants_result.fetchall()

    # Latest log entry per schema (DISTINCT ON is PostgreSQL-specific).
    logs_result = await db.execute(
        text(
            "SELECT DISTINCT ON (schema_name) "
            "    schema_name, status, error_message, finished_at "
            "FROM public.tenant_migration_log "
            "ORDER BY schema_name, started_at DESC"
        )
    )
    logs: dict[str, object] = {row.schema_name: row for row in logs_result.fetchall()}

    statuses = []
    for row in tenants:
        tenant_id, name, schema_name = row
        current = await _get_current_revision(schema_name)
        log = logs.get(schema_name)
        statuses.append({
            "tenant_id": str(tenant_id),
            "tenant_name": name,
            "schema_name": schema_name,
            "current_revision": current,
            "head_revision": head,
            "is_current": current == head,
            "last_status": log.status if log else None,
            "last_migration_at": log.finished_at if log else None,
            "last_error": log.error_message if log else None,
        })

    return statuses


async def run_all_tenant_migrations() -> None:
    """Startup hook: discover all tenants and apply pending migrations."""
    logger.info("Checking tenant schema migrations…")
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text(
                    "SELECT id, schema_name, name FROM public.tenants "
                    "WHERE status NOT IN ('PERMANENTLY_DELETED', 'FAILED') "
                    "  AND schema_name IS NOT NULL "
                    "ORDER BY created_at"
                )
            )
            tenants = result.fetchall()
    except Exception as exc:
        logger.error("Could not fetch tenant list for migration check: %s", exc)
        return

    logger.info("Found %d tenant schemas to check", len(tenants))
    for tenant_id, schema_name, name in tenants:
        try:
            res = await migrate_tenant(schema_name, tenant_id=UUID(str(tenant_id)))
            if res["status"] == "current":
                logger.debug("%s already at head", schema_name)
        except Exception as exc:
            logger.error("Unexpected error during startup migration for %s: %s", schema_name, exc)

    logger.info("Tenant migration check complete")
