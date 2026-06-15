"""USN backfill — Phase 1 / Step 2.

Assigns USNs to *existing* students who do not yet have one.  Preview-first and
idempotent; existing USNs are never modified.

Flow
----
preview()  — read-only.  Derives each student's (school, admission_year, program)
             from the enrollment chain, computes per-triple effective next
             sequence (max of the live counter and the max sequence parsed from
             existing matching USNs), and projects USNs in memory.  No writes.
commit()   — re-runs derivation/validation, seeds counters in the DB from
             existing USNs (GREATEST, idempotent), allocates contiguous blocks
             via UsnAllocator, and writes USNs *only* to students whose usn IS
             NULL.  Atomic: any failure rolls back the whole run.  A
             sis_import_batches row (record_type=USN_BACKFILL) is recorded for
             traceability.

Academic identity is derived, never stored redundantly:
  enrollment → section → semester → batch → program → department → school
admission_year for the USN year segment comes from acad_batches.start_year.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.onboarding.schemas import (
    UsnBackfillCommitResult,
    UsnBackfillPreviewResponse,
    UsnBackfillRow,
    UsnProjectedRange,
)
from app.core.onboarding.usn_allocator import UsnAllocator

# Derivation query — LEFT JOINs from users so unresolved students are still
# returned (and reported as ERROR) rather than silently dropped.
_DERIVE_SQL = text(
    """
    SELECT
        u.id              AS user_id,
        u.full_name       AS full_name,
        u.email           AS email,
        sp.usn            AS existing_usn,
        sp.admission_year AS profile_year,
        sch.code          AS school_code,
        p.code            AS program_code,
        b.start_year      AS batch_year
    FROM users u
    LEFT JOIN acad_enrollments  e   ON e.student_id  = u.id AND e.is_active = true
    LEFT JOIN acad_sections     sec ON sec.id        = e.section_id
    LEFT JOIN acad_semesters    sem ON sem.id        = sec.semester_id
    LEFT JOIN acad_batches      b   ON b.id          = sem.batch_id
    LEFT JOIN acad_programs     p   ON p.id          = b.program_id
    LEFT JOIN acad_departments  d   ON d.id          = p.department_id
    LEFT JOIN sis_schools       sch ON sch.id        = d.school_id
    LEFT JOIN sis_student_profiles sp ON sp.user_id  = u.id
    WHERE u.role = 'STUDENT' AND u.is_active = true
    ORDER BY u.full_name, u.id
    """
)

_SEED_SQL = text(
    """
    INSERT INTO usn_sequence_counters
        (school_code, admission_year, program_code, next_seq)
    VALUES (:school_code, :admission_year, :program_code, :seed_next)
    ON CONFLICT (school_code, admission_year, program_code)
    DO UPDATE SET next_seq   = GREATEST(usn_sequence_counters.next_seq, :seed_next),
                  updated_at = now()
    """
)

# Never overwrites an existing USN: the WHERE clause on DO UPDATE only fires when
# the stored usn is still NULL.  admission_year is filled only when absent.
_WRITE_SQL = text(
    """
    INSERT INTO sis_student_profiles (user_id, usn, admission_year)
    VALUES (:user_id, :usn, :admission_year)
    ON CONFLICT (user_id)
    DO UPDATE SET usn            = EXCLUDED.usn,
                  admission_year = COALESCE(sis_student_profiles.admission_year,
                                            EXCLUDED.admission_year),
                  updated_at     = now()
    WHERE sis_student_profiles.usn IS NULL
    """
)


def _prefix(school_code: str, batch_year: int, program_code: str) -> str:
    return f"{school_code.upper()}{int(batch_year) % 100:02d}{program_code.upper()}"


class UsnBackfillService:

    # ------------------------------------------------------------------ #
    # Shared derivation + seeding analysis                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _load_rows(db: AsyncSession) -> list[dict]:
        result = await db.execute(_DERIVE_SQL)
        return [dict(r) for r in result.mappings().all()]

    @staticmethod
    def _analyse(rows: list[dict]) -> tuple[dict[tuple, int], set[str]]:
        """Return (seed_max, taken_usns).

        seed_max[(school, year, program)] = highest sequence parsed from existing
        USNs that match that triple's prefix.  taken_usns = every existing USN
        (upper-cased) for global conflict detection.
        """
        seed_max: dict[tuple, int] = {}
        taken: set[str] = set()
        for r in rows:
            usn = (r["existing_usn"] or "").strip().upper()
            if not usn:
                continue
            taken.add(usn)
            sc, pc, yr = r["school_code"], r["program_code"], r["batch_year"]
            if not (sc and pc and yr is not None):
                continue  # USN cannot be attributed to a triple — skip seeding
            pfx = _prefix(sc, yr, pc)
            if usn.startswith(pfx):
                tail = usn[len(pfx):]
                if tail.isdigit():
                    key = (sc.upper(), int(yr), pc.upper())
                    seed_max[key] = max(seed_max.get(key, 0), int(tail))
        return seed_max, taken

    @staticmethod
    async def _load_counters(db: AsyncSession) -> dict[tuple, int]:
        result = await db.execute(
            text("SELECT school_code, admission_year, program_code, next_seq "
                 "FROM usn_sequence_counters")
        )
        return {
            (r["school_code"].upper(), int(r["admission_year"]), r["program_code"].upper()): int(r["next_seq"])
            for r in result.mappings().all()
        }

    # ------------------------------------------------------------------ #
    # Preview (read-only)                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def preview(db: AsyncSession) -> UsnBackfillPreviewResponse:
        rows = await UsnBackfillService._load_rows(db)
        seed_max, taken = UsnBackfillService._analyse(rows)
        counters = await UsnBackfillService._load_counters(db)

        # Effective next sequence per triple = max(live counter, seed+1, 1)
        def effective_next(key: tuple) -> int:
            return max(counters.get(key, 1), seed_max.get(key, 0) + 1, 1)

        # First pass: classify every student.
        out_rows: list[UsnBackfillRow] = []
        to_assign: dict[tuple, list[UsnBackfillRow]] = {}
        already = errors = conflicts = warnings = 0

        for r in rows:
            row = UsnBackfillRow(
                user_id=r["user_id"],
                full_name=r["full_name"],
                email=r["email"],
                school_code=r["school_code"],
                program_code=r["program_code"],
                admission_year=r["batch_year"],
                existing_usn=(r["existing_usn"] or None),
                action="",
            )

            if row.existing_usn:
                row.action = "SKIP_HAS_USN"
                already += 1
                out_rows.append(row)
                continue

            missing = []
            if not r["school_code"]:
                missing.append("school code (no school linked to department)")
            if not r["program_code"]:
                missing.append("program code")
            if r["batch_year"] is None:
                missing.append("batch/admission year (no active enrollment)")
            if missing:
                row.action = "ERROR"
                row.errors.append("cannot derive USN — missing: " + ", ".join(missing))
                errors += 1
                out_rows.append(row)
                continue

            if r["profile_year"] is not None and int(r["profile_year"]) != int(r["batch_year"]):
                row.warnings.append(
                    f"profile admission_year {r['profile_year']} differs from batch "
                    f"start_year {r['batch_year']} — USN uses the batch year"
                )
                warnings += 1

            key = (r["school_code"].upper(), int(r["batch_year"]), r["program_code"].upper())
            to_assign.setdefault(key, []).append(row)

        # Second pass: project USNs per triple in deterministic order.
        projected_ranges: list[UsnProjectedRange] = []
        for key, members in to_assign.items():
            sc, yr, pc = key
            seq = effective_next(key)
            assigned_here: list[str] = []
            for row in members:
                candidate = UsnAllocator.format_usn(sc, yr, pc, seq)
                if candidate in taken:
                    row.action = "CONFLICT"
                    row.errors.append(f"projected USN {candidate} already exists")
                    conflicts += 1
                    seq += 1  # advance so the rest stay contiguous
                    continue
                row.action = "ASSIGN"
                row.projected_usn = candidate
                taken.add(candidate)        # reserve within this preview run
                assigned_here.append(candidate)
                seq += 1
            if assigned_here:
                projected_ranges.append(UsnProjectedRange(
                    school_code=sc, admission_year=yr, program_code=pc,
                    seed_next_seq=effective_next(key),
                    count=len(assigned_here),
                    first_usn=assigned_here[0],
                    last_usn=assigned_here[-1],
                ))

        # out_rows so far holds only SKIP/ERROR rows; append the assign/conflict rows
        out_rows.extend(m for ms in to_assign.values() for m in ms)
        assign_total = sum(1 for r in out_rows if r.action == "ASSIGN")

        projected_ranges.sort(key=lambda x: (x.school_code, x.admission_year, x.program_code))
        out_rows.sort(key=lambda r: (r.full_name, str(r.user_id)))

        return UsnBackfillPreviewResponse(
            total_students=len(rows),
            already_have_usn=already,
            to_assign=assign_total,
            errors_count=errors,
            conflicts_count=conflicts,
            warnings_count=warnings,
            projected_ranges=projected_ranges,
            rows=out_rows,
        )

    # ------------------------------------------------------------------ #
    # Commit (atomic, idempotent)                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def commit(
        db: AsyncSession,
        *,
        actor_user_id: UUID,
    ) -> UsnBackfillCommitResult:
        from app.modules.m11_sis.import_batch_service import ImportBatchService

        rows = await UsnBackfillService._load_rows(db)
        seed_max, taken = UsnBackfillService._analyse(rows)

        # 1. Seed counters from existing USNs (idempotent GREATEST).
        counters_seeded = 0
        for (sc, yr, pc), mx in seed_max.items():
            await db.execute(_SEED_SQL, {
                "school_code": sc, "admission_year": yr,
                "program_code": pc, "seed_next": mx + 1,
            })
            counters_seeded += 1

        # 2. Group assignable students by triple (skip rows with USN / errors).
        to_assign: dict[tuple, list[dict]] = {}
        skipped = failed = 0
        errors: list[str] = []
        for r in rows:
            if (r["existing_usn"] or "").strip():
                skipped += 1
                continue
            if not (r["school_code"] and r["program_code"] and r["batch_year"] is not None):
                failed += 1
                errors.append(f"{r['email']}: cannot derive USN (missing school/program/year)")
                continue
            key = (r["school_code"].upper(), int(r["batch_year"]), r["program_code"].upper())
            to_assign.setdefault(key, []).append(r)

        # 3. Allocate a contiguous block per triple and write USNs.
        assigned = 0
        for key, members in to_assign.items():
            sc, yr, pc = key
            members.sort(key=lambda m: (m["full_name"], str(m["user_id"])))
            start = await UsnAllocator.allocate_block(
                db, school_code=sc, admission_year=yr, program_code=pc, count=len(members),
            )
            for i, m in enumerate(members):
                usn = UsnAllocator.format_usn(sc, yr, pc, start + i)
                if usn in taken:
                    failed += 1
                    errors.append(f"{m['email']}: USN {usn} already exists — skipped")
                    continue
                res = await db.execute(_WRITE_SQL, {
                    "user_id": str(m["user_id"]), "usn": usn, "admission_year": yr,
                })
                if res.rowcount and res.rowcount > 0:
                    assigned += 1
                    taken.add(usn)
                else:
                    # Row already had a USN (race / concurrent) — treat as skipped.
                    skipped += 1

        # 4. Record an import batch for traceability.
        batch_ref = None
        if assigned > 0:
            batch = await ImportBatchService.create_batch(
                imported_by=actor_user_id,
                record_type="USN_BACKFILL",
                total_records=len(rows),
                success_count=assigned,
                failed_count=failed,
                db=db,
            )
            batch_ref = batch.batch_ref

        # No explicit commit here: the caller's transaction boundary (the
        # _admin_db dependency's `session.begin()`) commits the whole run
        # atomically, so any failure rolls everything back.
        return UsnBackfillCommitResult(
            total_students=len(rows),
            assigned=assigned,
            skipped=skipped,
            failed=failed,
            counters_seeded=counters_seeded,
            batch_ref=batch_ref,
            errors=errors,
        )
