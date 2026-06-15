"""USN minting for the import pipeline — ERP Onboarding Phase 1 / Step 4.

Shared helpers that let the student-import flow project and mint USNs using
``UsnAllocator`` exclusively, mirroring the semantics of the Step 2 backfill but
driven by the *import context* (resolved program + section/batch) rather than an
already-persisted enrollment chain — because at import time the students don't
exist yet.

Two phases, matching the preview-first contract:

* ``project_usns`` — read-only.  Computes the per-triple effective next sequence
  (max of the live counter and the highest sequence already present on
  ``sis_student_profiles``) and projects USNs in memory.  No writes.
* ``mint_usns``    — seeds the counter from existing USNs (idempotent GREATEST),
  reserves a contiguous block per triple via ``UsnAllocator.allocate_block`` and
  writes USNs only to profiles whose ``usn IS NULL``.  Runs inside the caller's
  transaction, so an aborted commit releases the reserved numbers.

A "triple" is ``(school_code, admission_year, program_code)`` — the same key the
allocator and the USN sequence counters use; the sequence resets per triple.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.onboarding.usn_allocator import UsnAllocator

# Idempotent counter seed — advance the triple's counter to at least max+1 of the
# USNs already issued for it.  Identical semantics to the backfill _SEED_SQL.
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

# Writes a USN only when the profile has none yet (idempotent / never overwrites).
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

Triple = tuple[str, int, str]  # (school_code, admission_year, program_code)


@dataclass
class MintItem:
    """One student queued for USN assignment."""
    triple: Triple
    user_id: UUID
    full_name: str
    email: str


@dataclass
class ProjectItem:
    """One student queued for USN projection (preview).  ``projected`` is filled in."""
    triple: Triple
    full_name: str
    email: str
    projected: str | None = None


@dataclass
class ProjectedRange:
    school_code: str
    admission_year: int
    program_code: str
    count: int
    first_usn: str
    last_usn: str


def _prefix(school_code: str, admission_year: int, program_code: str) -> str:
    return f"{school_code.upper()}{int(admission_year) % 100:02d}{program_code.upper()}"


async def _load_taken(db: AsyncSession) -> set[str]:
    rows = await db.execute(
        text("SELECT usn FROM sis_student_profiles WHERE usn IS NOT NULL")
    )
    return {(r[0] or "").strip().upper() for r in rows.fetchall() if r[0]}


async def _existing_max_seq(db: AsyncSession, triple: Triple) -> int:
    """Highest sequence already issued for this triple's prefix (0 if none)."""
    sc, yr, pc = triple
    pfx = _prefix(sc, yr, pc)
    rows = await db.execute(
        text("SELECT usn FROM sis_student_profiles WHERE UPPER(usn) LIKE :pfx"),
        {"pfx": pfx + "%"},
    )
    mx = 0
    for r in rows.fetchall():
        usn = (r[0] or "").strip().upper()
        tail = usn[len(pfx):]
        if tail.isdigit():
            mx = max(mx, int(tail))
    return mx


async def _counter_next(db: AsyncSession, triple: Triple) -> int:
    sc, yr, pc = triple
    row = await db.execute(
        text(
            "SELECT next_seq FROM usn_sequence_counters "
            "WHERE UPPER(school_code) = :sc AND admission_year = :yr "
            "AND UPPER(program_code) = :pc"
        ),
        {"sc": sc.upper(), "yr": int(yr), "pc": pc.upper()},
    )
    val = row.scalar_one_or_none()
    return int(val) if val is not None else 1


def _group(items: list) -> dict[Triple, list]:
    """Group by triple, members sorted deterministically by (full_name, email)."""
    groups: dict[Triple, list] = {}
    for it in items:
        groups.setdefault(it.triple, []).append(it)
    for members in groups.values():
        members.sort(key=lambda m: (m.full_name or "", m.email or ""))
    return groups


# ---------------------------------------------------------------------------
# Preview projection (read-only)
# ---------------------------------------------------------------------------

async def project_usns(
    db: AsyncSession, items: list[ProjectItem]
) -> list[ProjectedRange]:
    """Fill ``ProjectItem.projected`` for each item; return per-triple ranges.

    Read-only.  Effective next sequence = max(live counter, existing max + 1, 1).
    Defensive conflict handling: if a projected USN already exists, the slot is
    skipped (projected left None) and the sequence advances so the rest stay
    contiguous — this should not happen in practice because the effective next
    already clears the existing max.
    """
    taken = await _load_taken(db)
    ranges: list[ProjectedRange] = []

    for triple, members in _group(items).items():
        sc, yr, pc = triple
        seq = max(await _counter_next(db, triple), await _existing_max_seq(db, triple) + 1, 1)
        assigned: list[str] = []
        for m in members:
            cand = UsnAllocator.format_usn(sc, yr, pc, seq)
            if cand in taken:
                seq += 1
                continue
            m.projected = cand
            taken.add(cand)
            assigned.append(cand)
            seq += 1
        if assigned:
            ranges.append(ProjectedRange(
                school_code=sc, admission_year=yr, program_code=pc,
                count=len(assigned), first_usn=assigned[0], last_usn=assigned[-1],
            ))

    ranges.sort(key=lambda r: (r.school_code, r.admission_year, r.program_code))
    return ranges


# ---------------------------------------------------------------------------
# Commit minting (writes; inside caller's transaction)
# ---------------------------------------------------------------------------

async def mint_usns(
    db: AsyncSession, items: list[MintItem]
) -> tuple[dict[UUID, str], int]:
    """Allocate + persist USNs for the given students.

    Returns ``(user_id -> usn, assigned_count)``.  USNs are written only to
    profiles whose ``usn IS NULL``; a slot whose USN somehow already exists is
    skipped (not counted).  No commit here — the caller's transaction commits.
    """
    if not items:
        return {}, 0

    taken = await _load_taken(db)
    out: dict[UUID, str] = {}
    assigned = 0

    for triple, members in _group(items).items():
        sc, yr, pc = triple
        # Seed the counter from any USNs already issued (idempotent), so a fresh
        # counter continues past legacy/backfilled USNs instead of colliding.
        mx = await _existing_max_seq(db, triple)
        if mx > 0:
            await db.execute(_SEED_SQL, {
                "school_code": sc, "admission_year": yr,
                "program_code": pc, "seed_next": mx + 1,
            })
        start = await UsnAllocator.allocate_block(
            db, school_code=sc, admission_year=yr, program_code=pc, count=len(members),
        )
        for i, m in enumerate(members):
            usn = UsnAllocator.format_usn(sc, yr, pc, start + i)
            if usn in taken:
                continue
            res = await db.execute(_WRITE_SQL, {
                "user_id": str(m.user_id), "usn": usn, "admission_year": yr,
            })
            if res.rowcount and res.rowcount > 0:
                out[m.user_id] = usn
                taken.add(usn)
                assigned += 1

    return out, assigned
