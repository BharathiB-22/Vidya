"""
upgrade_all_tenants.py — Forward-migrate all ACTIVE tenant schemas to Alembic head.

Run from the backend/ directory:

    python -m app.management.upgrade_all_tenants

Options
-------
--dry-run
    List tenants that would be upgraded without executing any migration.

--include-failed
    Also attempt upgrade for tenants in FAILED provisioning state.
    Useful when a tenant provisioning failed mid-migration and left a partial schema.

--schema SCHEMA_NAME
    Upgrade a single named schema only (e.g. tenant_bvs_university).
    Useful for targeted one-off fixes.

Exit codes
----------
0  All targeted tenant schemas are now at migration head (or --dry-run ran).
1  One or more tenant schema upgrades failed.

Safety invariants
-----------------
* Upgrades are sequential — one tenant at a time. No concurrent env-var mutation.
* The upgrade is idempotent: tenants already at head are skipped automatically
  by Alembic (no-op, no error).
* Tenant status in public.tenants is NEVER modified by this script.
  Active tenants stay ACTIVE; failed tenants stay FAILED.
* Only schemas whose schema_name starts with 'tenant_' are processed.
  Any unexpected schema_name fails the safety check and is skipped with a warning.
"""

import argparse
import logging
import sys
import time
from dataclasses import dataclass

from sqlalchemy import create_engine, text

from app.config import settings
# _migrate_sync is the synchronous Alembic runner used by the async provisioner.
# Importing it here is intentional: this management script runs outside the
# asyncio event loop, so we call the underlying sync function directly.
from app.core.tenants.provisioner import _migrate_sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("vidya.upgrade_tenants")

_SCHEMA_PATTERN = "tenant_"


@dataclass
class TenantRow:
    schema_name: str
    slug: str
    name: str
    status: str


def _fetch_tenants(include_failed: bool, single_schema: str | None) -> list[TenantRow]:
    statuses = ["ACTIVE"]
    if include_failed:
        statuses.append("FAILED")

    placeholders = ", ".join(f":s{i}" for i in range(len(statuses)))
    params: dict = {f"s{i}": s for i, s in enumerate(statuses)}

    where_clause = f"status IN ({placeholders})"
    if single_schema:
        where_clause += " AND schema_name = :target_schema"
        params["target_schema"] = single_schema

    sql = (
        "SELECT schema_name, slug, name, status "
        "FROM public.tenants "
        f"WHERE {where_clause} "
        "ORDER BY created_at ASC"
    )

    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql), params)
            return [
                TenantRow(
                    schema_name=row[0],
                    slug=row[1],
                    name=row[2],
                    status=row[3],
                )
                for row in result
            ]
    finally:
        engine.dispose()


def _is_safe_schema(schema_name: str) -> bool:
    """Guard: only process schemas that follow the tenant_ naming convention."""
    return bool(schema_name) and schema_name.startswith(_SCHEMA_PATTERN)


def _upgrade_one(tenant: TenantRow) -> tuple[bool, str]:
    """Attempt to upgrade one tenant schema. Returns (success, message)."""
    try:
        _migrate_sync(tenant.schema_name)
        return True, "at head"
    except Exception as exc:
        return False, str(exc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="upgrade_all_tenants",
        description="Forward-migrate all active tenant schemas to the latest Alembic head.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List tenants without running any migration.",
    )
    parser.add_argument(
        "--include-failed",
        action="store_true",
        help="Also attempt upgrade for tenants in FAILED provisioning state.",
    )
    parser.add_argument(
        "--schema",
        metavar="SCHEMA_NAME",
        help="Upgrade only this schema (e.g. tenant_bvs_university).",
    )
    args = parser.parse_args(argv)

    logger.info("=" * 60)
    logger.info("Vidya — Tenant Schema Upgrade")
    logger.info("=" * 60)

    tenants = _fetch_tenants(include_failed=args.include_failed, single_schema=args.schema)

    if not tenants:
        if args.schema:
            logger.warning(
                "No tenant found with schema_name='%s' in targeted statuses. "
                "Check the slug or add --include-failed if the tenant is in FAILED state.",
                args.schema,
            )
        else:
            logger.info("No tenants found to upgrade.")
        return 0

    logger.info("Tenants targeted: %d", len(tenants))
    for t in tenants:
        logger.info("  • %-36s [%-11s] %s", t.schema_name, t.status, t.name)
    logger.info("")

    if args.dry_run:
        logger.info("Dry run — no migrations executed.")
        return 0

    failed: list[tuple[str, str]] = []
    succeeded: list[str] = []
    skipped: list[str] = []

    for idx, tenant in enumerate(tenants, start=1):
        logger.info(
            "[%d/%d] Upgrading: %s  (%s)",
            idx,
            len(tenants),
            tenant.schema_name,
            tenant.name,
        )

        if not _is_safe_schema(tenant.schema_name):
            logger.warning(
                "        SKIPPED — schema_name '%s' does not follow the tenant_ "
                "naming convention. Manual review required.",
                tenant.schema_name,
            )
            skipped.append(tenant.slug)
            continue

        t0 = time.monotonic()
        success, msg = _upgrade_one(tenant)
        elapsed = time.monotonic() - t0

        if success:
            logger.info("        OK — %s  (%.1fs)", msg, elapsed)
            succeeded.append(tenant.slug)
        else:
            logger.error("        FAILED  (%.1fs): %s", elapsed, msg)
            failed.append((tenant.slug, msg))

    logger.info("")
    logger.info("=" * 60)
    logger.info(
        "Results: %d succeeded / %d failed / %d skipped / %d total",
        len(succeeded),
        len(failed),
        len(skipped),
        len(tenants),
    )

    if failed:
        logger.error("Failed tenants:")
        for slug, msg in failed:
            logger.error("  • %s: %s", slug, msg)
        logger.info("=" * 60)
        return 1

    logger.info("All tenant schemas are now at migration head.")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
