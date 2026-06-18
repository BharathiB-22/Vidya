"""
backfill_institution_emails.py — Populate institution_email for students who have
a USN but no institution_email.

For each active tenant that has institution_domain configured:
    UPDATE users
       SET institution_email = lower(usn) || '@' || domain,
           personal_email     = COALESCE(personal_email, email)
      FROM sis_student_profiles sp
     WHERE users.id              = sp.user_id
       AND users.role            = 'STUDENT'
       AND users.institution_email IS NULL
       AND sp.usn IS NOT NULL

Run from backend/ directory:
    python -m app.management.backfill_institution_emails           # preview (default)
    python -m app.management.backfill_institution_emails --commit  # apply

Exit codes: 0 = success, 1 = error.
"""
from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import create_engine, text

from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("vidya.backfill_emails")

# Preview query — count eligible students per tenant
_PREVIEW_SQL = text(
    """
    SELECT
        COUNT(*) FILTER (WHERE u.institution_email IS NULL AND sp.usn IS NOT NULL) AS to_assign,
        COUNT(*) FILTER (WHERE u.institution_email IS NOT NULL)                     AS already_have,
        COUNT(*) FILTER (WHERE sp.usn IS NULL AND u.institution_email IS NULL)      AS no_usn
    FROM {schema}.users u
    LEFT JOIN {schema}.sis_student_profiles sp ON sp.user_id = u.id
    WHERE u.role = 'STUDENT' AND u.is_active = true
    """
)

# Sample of students that will be affected (preview)
_SAMPLE_SQL = text(
    """
    SELECT u.full_name, u.email, sp.usn,
           lower(sp.usn) || '@' || :domain AS projected_inst
    FROM {schema}.users u
    JOIN {schema}.sis_student_profiles sp ON sp.user_id = u.id
    WHERE u.role = 'STUDENT'
      AND u.institution_email IS NULL
      AND sp.usn IS NOT NULL
    ORDER BY sp.usn
    LIMIT 3
    """
)

# Commit query — idempotent UPDATE
_COMMIT_SQL = text(
    """
    UPDATE {schema}.users u
       SET institution_email = lower(sp.usn) || '@' || :domain,
           personal_email     = COALESCE(u.personal_email, u.email)
      FROM {schema}.sis_student_profiles sp
     WHERE u.id = sp.user_id
       AND u.role = 'STUDENT'
       AND u.institution_email IS NULL
       AND sp.usn IS NOT NULL
    """
)


def _fmt_sql(raw: text, schema: str) -> text:
    return text(str(raw).replace("{schema}", schema))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backfill_institution_emails",
        description=(
            "Populate institution_email for students who have a USN "
            "but no institution_email."
        ),
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
            tenants = conn.execute(
                text(
                    "SELECT slug, name, schema_name, institution_domain "
                    "FROM public.tenants "
                    "WHERE status = 'ACTIVE' AND institution_domain IS NOT NULL "
                    "ORDER BY slug"
                )
            ).fetchall()
            no_domain = conn.execute(
                text(
                    "SELECT slug FROM public.tenants "
                    "WHERE status = 'ACTIVE' AND institution_domain IS NULL "
                    "ORDER BY slug"
                )
            ).fetchall()
    finally:
        engine.dispose()

    logger.info("=" * 60)
    logger.info("Institution Email Backfill — %s", "COMMIT" if args.commit else "PREVIEW")
    logger.info("=" * 60)

    if no_domain:
        logger.warning(
            "Skipped (%d tenants have no domain — run backfill_institution_domains first):",
            len(no_domain),
        )
        for r in no_domain:
            logger.warning("  %s", r[0])
        logger.info("")

    if not tenants:
        logger.info("No eligible tenants found (no active tenant has institution_domain set).")
        return 0

    total_to_assign = 0
    total_assigned  = 0

    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    try:
        # Fetch existing schemas once to skip tenants whose schema was never created.
        with engine.connect() as conn:
            existing_schemas = {
                r[0] for r in conn.execute(
                    text("SELECT schema_name FROM information_schema.schemata")
                ).fetchall()
            }

        for slug, name, schema, domain in tenants:
            if schema not in existing_schemas:
                logger.warning("  SKIPPED %s — schema '%s' does not exist", slug, schema)
                logger.info("")
                continue
            with engine.connect() as conn:
                row = conn.execute(
                    _fmt_sql(_PREVIEW_SQL, schema),
                ).one()
                to_assign   = row[0] or 0
                already     = row[1] or 0
                no_usn      = row[2] or 0
                total_to_assign += to_assign

                logger.info(
                    "%s  (%s)  domain=%s",
                    slug, name, domain,
                )
                logger.info(
                    "  to_assign=%d  already_have=%d  no_usn=%d",
                    to_assign, already, no_usn,
                )

                if to_assign > 0:
                    samples = conn.execute(
                        _fmt_sql(_SAMPLE_SQL, schema),
                        {"domain": domain},
                    ).fetchall()
                    for s in samples:
                        logger.info(
                            "  sample: %s  %s  ->  %s",
                            s[2], s[1], s[3],
                        )

            if args.commit and to_assign > 0:
                with engine.begin() as conn:
                    result = conn.execute(
                        _fmt_sql(_COMMIT_SQL, schema),
                        {"domain": domain},
                    )
                    assigned = result.rowcount or 0
                    total_assigned += assigned
                    logger.info("  COMMITTED: %d rows updated", assigned)

            logger.info("")
    finally:
        engine.dispose()

    logger.info("=" * 60)
    if args.commit:
        logger.info("Total updated: %d students across %d tenants", total_assigned, len(tenants))
    else:
        logger.info(
            "Preview: %d students eligible across %d tenants. Pass --commit to apply.",
            total_to_assign, len(tenants),
        )
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
