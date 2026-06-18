"""
backfill_import_history_context.py — Repair historical SisImportBatch context.

Run from backend/ directory:

    python -m app.management.backfill_import_history_context --schema tenant_vbs_university
    python -m app.management.backfill_import_history_context          # all active tenants

Reconstruction logic
--------------------
For each SisImportBatch where program_name IS NULL:

1. Find every SisStudentProfile linked via import_batch_id.
2. Follow their ACTIVE acad_enrollments through:
       acad_sections → acad_semesters → acad_batches → acad_programs
3. Collect the DISTINCT (program_id, batch_id, semester_id, section_id) tuples.

   • Exactly 1 unique tuple  → backfill all 8 context columns confidently.
   • More than 1 unique tuple → program_name = 'Mixed Import', IDs left NULL.
   • 0 students / 0 enrollments → skip (unresolved, logged).

Safety invariants
-----------------
* Only rows where program_name IS NULL are touched. Already-repaired rows
  (including the sentinel 'Mixed Import') are never re-processed.
* Idempotent: re-running produces the same result.
* Uses psycopg2 (synchronous) — no asyncio, no FastAPI dependencies.
* --dry-run flag prints what would change without writing anything.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from typing import Optional

import psycopg2
import psycopg2.extras

from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
_log = logging.getLogger("vidya.backfill_import_ctx")

# ---------------------------------------------------------------------------
# SQL — list active tenant schemas
# ---------------------------------------------------------------------------

_LIST_TENANTS_SQL = """
SELECT schema_name, slug, name
FROM   public.tenants
WHERE  status = 'ACTIVE'
  AND  schema_name LIKE 'tenant\\_%' ESCAPE '\\'
ORDER  BY created_at ASC
"""

_LIST_TENANTS_SINGLE_SQL = """
SELECT schema_name, slug, name
FROM   public.tenants
WHERE  status = 'ACTIVE'
  AND  schema_name = %(schema)s
"""

# ---------------------------------------------------------------------------
# SQL — find NULL-context batches in a given tenant schema
# ---------------------------------------------------------------------------

_NULL_BATCHES_SQL = """
SELECT id, batch_ref, record_type, success_count
FROM   {schema}.sis_import_batches
WHERE  program_name IS NULL
ORDER  BY imported_at ASC
"""

# ---------------------------------------------------------------------------
# SQL — reconstruct context for one batch
#
# Returns one row per distinct (program, batch, semester, section) combination
# across ALL enrolled students in this batch.  If a student has multiple
# active enrollments (e.g. moved sections) we take the most-recent one via
# MAX(e.id) — enrollment IDs are UUIDs so recency isn't strictly guaranteed,
# but in practice the latest INSERT wins and section moves are rare.
# ---------------------------------------------------------------------------

_RECONSTRUCT_SQL = """
WITH
enrolled AS (
    -- One row per student: their most-relevant active section
    SELECT DISTINCT ON (e.student_id)
        e.student_id,
        e.section_id
    FROM   {schema}.sis_student_profiles sp
    JOIN   {schema}.acad_enrollments     e   ON e.student_id = sp.user_id
                                             AND e.is_active  = true
    WHERE  sp.import_batch_id = %(batch_id)s
    ORDER  BY e.student_id, e.enrolled_at DESC NULLS LAST, e.id DESC
),
context AS (
    SELECT DISTINCT
        p.id   AS program_id,
        p.name AS program_name,
        b.id   AS batch_id,
        b.name AS batch_name,
        sem.id     AS semester_id,
        sem.number AS semester_number,
        sem.label  AS semester_label,
        sec.id   AS section_id,
        sec.name AS section_name
    FROM  enrolled
    JOIN  {schema}.acad_sections  sec ON sec.id  = enrolled.section_id
    JOIN  {schema}.acad_semesters sem ON sem.id  = sec.semester_id
    JOIN  {schema}.acad_batches   b   ON b.id    = sem.batch_id
    JOIN  {schema}.acad_programs  p   ON p.id    = b.program_id
)
SELECT * FROM context
"""

# ---------------------------------------------------------------------------
# SQL — apply backfill
# ---------------------------------------------------------------------------

_UPDATE_SINGLE_SQL = """
UPDATE {schema}.sis_import_batches
SET
    program_id    = %(program_id)s,
    program_name  = %(program_name)s,
    batch_id      = %(batch_id)s,
    batch_name    = %(batch_name)s,
    semester_id   = %(semester_id)s,
    semester_name = %(semester_name)s,
    section_id    = %(section_id)s,
    section_name  = %(section_name)s
WHERE id = %(id)s
  AND program_name IS NULL
"""

_UPDATE_MIXED_SQL = """
UPDATE {schema}.sis_import_batches
SET    program_name = 'Mixed Import'
WHERE  id = %(id)s
  AND  program_name IS NULL
"""

# ---------------------------------------------------------------------------
# Result counters
# ---------------------------------------------------------------------------

@dataclass
class TenantResult:
    schema:     str
    examined:   int = 0
    repaired:   int = 0
    mixed:      int = 0
    unresolved: int = 0
    errors:     list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _sync_url() -> str:
    """Return a plain postgresql:// DSN for psycopg2.connect()."""
    # SYNC_DATABASE_URL = "postgresql+psycopg2://..." — SQLAlchemy prefix;
    # psycopg2.connect() needs the plain "postgresql://" form.
    url = settings.SYNC_DATABASE_URL
    return url.replace("postgresql+psycopg2://", "postgresql://", 1)


def _process_tenant(
    conn: "psycopg2.connection",
    schema: str,
    dry_run: bool,
) -> TenantResult:
    result = TenantResult(schema=schema)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # 1. Find NULL-context batches
        cur.execute(_NULL_BATCHES_SQL.format(schema=schema))
        batches = cur.fetchall()
        result.examined = len(batches)

        if not batches:
            _log.info("  %s: no NULL-context batches — nothing to do", schema)
            return result

        _log.info("  %s: %d NULL-context batch(es) to examine", schema, len(batches))

        for batch in batches:
            batch_id  = batch["id"]
            batch_ref = batch["batch_ref"]

            # 2. Reconstruct via enrollment chain
            cur.execute(
                _RECONSTRUCT_SQL.format(schema=schema),
                {"batch_id": str(batch_id)},
            )
            rows = cur.fetchall()

            if len(rows) == 0:
                # No enrolled students or no active enrollments found
                _log.warning(
                    "  %s  %-28s -> UNRESOLVED (no active enrollments found)",
                    schema, batch_ref,
                )
                result.unresolved += 1
                continue

            if len(rows) > 1:
                # Students span multiple program/batch/semester/section combos
                programs  = {r["program_name"] for r in rows}
                sections  = {r["section_name"]  for r in rows}
                _log.warning(
                    "  %s  %-28s -> MIXED (%d combos: programs=%s sections=%s)",
                    schema, batch_ref, len(rows), sorted(programs), sorted(sections),
                )
                result.mixed += 1
                if not dry_run:
                    cur.execute(_UPDATE_MIXED_SQL.format(schema=schema), {"id": str(batch_id)})
                    conn.commit()
                continue

            # Exactly one combination — safe to backfill
            ctx = rows[0]
            sem_name = ctx["semester_label"] or f"Semester {ctx['semester_number']}"
            batch_name_safe = (ctx["batch_name"] or "").replace("–", "-").replace("—", "-")
            _log.info(
                "  %s  %-28s -> %s | %s | %s | Section %s",
                schema, batch_ref,
                ctx["program_name"], batch_name_safe, sem_name, ctx["section_name"],
            )

            if not dry_run:
                cur.execute(
                    _UPDATE_SINGLE_SQL.format(schema=schema),
                    {
                        "id":           str(batch_id),
                        "program_id":   str(ctx["program_id"]),
                        "program_name": ctx["program_name"],
                        "batch_id":     str(ctx["batch_id"]),
                        "batch_name":   ctx["batch_name"],
                        "semester_id":  str(ctx["semester_id"]),
                        "semester_name": sem_name,
                        "section_id":   str(ctx["section_id"]),
                        "section_name": ctx["section_name"],
                    },
                )
                conn.commit()

            result.repaired += 1

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill academic context for historical SIS import batches.",
    )
    parser.add_argument(
        "--schema",
        metavar="SCHEMA_NAME",
        help="Target a single tenant schema (e.g. tenant_vbs_university).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would change without writing to the database.",
    )
    args = parser.parse_args(argv)

    sync_url = _sync_url()

    conn = psycopg2.connect(sync_url)
    conn.autocommit = False

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if args.schema:
                cur.execute(_LIST_TENANTS_SINGLE_SQL, {"schema": args.schema})
            else:
                cur.execute(_LIST_TENANTS_SQL)
            tenants = cur.fetchall()
    except Exception as exc:
        _log.error("Failed to list tenants: %s", exc)
        conn.close()
        return 1

    if not tenants:
        _log.warning("No matching active tenants found.")
        conn.close()
        return 0

    _log.info("=" * 64)
    _log.info("Import History Context Backfill%s", "  [DRY RUN]" if args.dry_run else "")
    _log.info("=" * 64)
    _log.info("Tenants targeted: %d", len(tenants))
    for t in tenants:
        _log.info("  • %s  (%s)", t["schema_name"], t["name"])
    _log.info("")

    all_results: list[TenantResult] = []

    for tenant in tenants:
        schema = tenant["schema_name"]
        _log.info("Processing: %s", schema)
        try:
            result = _process_tenant(conn, schema, dry_run=args.dry_run)
            all_results.append(result)
        except Exception as exc:
            _log.error("  ERROR processing %s: %s", schema, exc)
            conn.rollback()
            all_results.append(
                TenantResult(schema=schema, errors=[str(exc)])
            )

    conn.close()

    # Summary
    total_examined  = sum(r.examined   for r in all_results)
    total_repaired  = sum(r.repaired   for r in all_results)
    total_mixed     = sum(r.mixed      for r in all_results)
    total_unresolved = sum(r.unresolved for r in all_results)
    total_errors    = sum(len(r.errors) for r in all_results)

    _log.info("")
    _log.info("=" * 64)
    _log.info("RESULTS%s", "  (dry run — no writes)" if args.dry_run else "")
    _log.info("  Examined:   %d", total_examined)
    _log.info("  Repaired:   %d", total_repaired)
    _log.info("  Mixed:      %d", total_mixed)
    _log.info("  Unresolved: %d", total_unresolved)
    _log.info("  Errors:     %d", total_errors)
    _log.info("=" * 64)

    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
