"""
backfill_institution_domains.py — Set institution_domain for active tenants where NULL.

Derivation rule:
    lms-university   -> lms.edu
    dsu-university   -> dsu.edu
    innova-university-> innova.edu
    (no known suffix) -> {full-slug}.edu

Run from backend/ directory:
    python -m app.management.backfill_institution_domains           # preview (default)
    python -m app.management.backfill_institution_domains --commit  # apply

Exit codes: 0 = success, 1 = error.
"""
from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import create_engine, text

from app.config import settings
from app.core.tenants.provisioner import derive_institution_domain

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("vidya.backfill_domains")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backfill_institution_domains",
        description="Set institution_domain for active tenants that currently have NULL.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Apply changes. Default is preview (dry run).",
    )
    args = parser.parse_args(argv)

    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, slug, name, institution_domain "
                    "FROM public.tenants "
                    "WHERE status = 'ACTIVE' "
                    "ORDER BY slug"
                )
            ).fetchall()
    finally:
        engine.dispose()

    already_set = [(r[1], r[2], r[3]) for r in rows if r[3] is not None]
    to_set      = [(r[0], r[1], r[2], derive_institution_domain(r[1])) for r in rows if r[3] is None]

    logger.info("=" * 60)
    logger.info("Institution Domain Backfill — %s", "COMMIT" if args.commit else "PREVIEW")
    logger.info("=" * 60)

    if already_set:
        logger.info("Already configured (%d) — skipped:", len(already_set))
        for slug, name, dom in already_set:
            logger.info("  %-30s  %s  (%s)", slug, dom, name)

    if to_set:
        logger.info("\nWill set (%d):", len(to_set))
        for _, slug, name, dom in to_set:
            logger.info("  %-30s -> %s  (%s)", slug, dom, name)
    else:
        logger.info("\nAll active tenants already have institution_domain configured.")

    if not args.commit:
        logger.info("\nDry run — pass --commit to apply.")
        return 0

    if not to_set:
        return 0

    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    try:
        with engine.begin() as conn:
            for tid, slug, _, dom in to_set:
                conn.execute(
                    text(
                        "UPDATE public.tenants SET institution_domain = :d WHERE id = :id"
                    ),
                    {"d": dom, "id": str(tid)},
                )
    finally:
        engine.dispose()

    logger.info("\nUpdated %d tenants.", len(to_set))
    return 0


if __name__ == "__main__":
    sys.exit(main())
