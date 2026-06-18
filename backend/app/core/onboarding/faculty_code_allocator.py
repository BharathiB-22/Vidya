"""Faculty-code allocation — concurrency-safe sequence reservation.

Phase 1.5 of the Intelligent ERP Onboarding programme.

Faculty-code format:  ``{PREFIX}{Seq}``   e.g.  ``FAC0001`` (default prefix ``FAC``).

``allocate_block`` reserves a contiguous range of sequence numbers for a
``prefix`` using an atomic ``INSERT ... ON CONFLICT DO UPDATE ... RETURNING``.
The ON CONFLICT row lock serialises concurrent callers, so issued ranges never
overlap and contain no gaps.  Codes mint on commit only: call inside the same
transaction that writes the faculty rows, so an aborted commit releases the
reserved numbers (the counter increment rolls back with it).

Mirrors ``UsnAllocator``.  The allocator never edits an existing faculty_code —
it only hands out new numbers; faculty_code immutability is enforced at the
profile write layer.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_FACULTY_PREFIX = "FAC"


class FacultyCodeAllocatorError(ValueError):
    """Raised for invalid allocation arguments (bad count or empty prefix)."""


# In BOTH the insert and the conflict path the returned ``next_value`` is the
# value *after* incrementing by ``count``, so the start of the reserved block is
# always ``returned - count``:
#   • first insert → next_value = count + 1, start = 1
#   • on conflict  → next_value = prev + count, start = prev
_ALLOC_SQL = text(
    """
    INSERT INTO faculty_code_counters (prefix, next_value)
    VALUES (:prefix, :count + 1)
    ON CONFLICT (prefix)
    DO UPDATE SET next_value = faculty_code_counters.next_value + :count,
                  updated_at = now()
    RETURNING next_value
    """
)


class FacultyCodeAllocator:

    @staticmethod
    def _norm(prefix: str) -> str:
        p = (prefix or "").strip().upper()
        if not p:
            raise FacultyCodeAllocatorError("prefix is required")
        return p

    @staticmethod
    async def allocate_block(
        db: AsyncSession,
        *,
        prefix: str = DEFAULT_FACULTY_PREFIX,
        count: int,
    ) -> int:
        """Reserve ``count`` contiguous sequence numbers; return the first one.

        The reserved block is ``[start, start + count - 1]``.  Atomic and safe
        under concurrent callers sharing the same prefix.
        """
        if count < 1:
            raise FacultyCodeAllocatorError("count must be >= 1")
        p = FacultyCodeAllocator._norm(prefix)
        result = await db.execute(_ALLOC_SQL, {"prefix": p, "count": int(count)})
        new_next = int(result.scalar_one())
        return new_next - count

    @staticmethod
    def format_code(prefix: str, seq: int, *, width: int = 4) -> str:
        """Render a faculty code, e.g. ``FAC0001``."""
        p = FacultyCodeAllocator._norm(prefix)
        if seq < 1:
            raise FacultyCodeAllocatorError("seq must be >= 1")
        return f"{p}{seq:0{width}d}"

    @staticmethod
    async def allocate_codes(
        db: AsyncSession,
        *,
        prefix: str = DEFAULT_FACULTY_PREFIX,
        count: int,
        width: int = 4,
    ) -> list[str]:
        """Reserve ``count`` faculty codes and return the formatted strings, in order."""
        start = await FacultyCodeAllocator.allocate_block(db, prefix=prefix, count=count)
        return [
            FacultyCodeAllocator.format_code(prefix, start + i, width=width)
            for i in range(count)
        ]

    @staticmethod
    async def seed_counter_from_existing(
        db: AsyncSession,
        *,
        prefix: str = DEFAULT_FACULTY_PREFIX,
    ) -> None:
        """Advance the counter past the highest existing faculty_code for this prefix.

        Idempotent.  Lets backfill/imports resume contiguously when codes already
        exist (e.g. after a prior partial run).  Uses GREATEST so it never lowers
        an already-higher counter.
        """
        p = FacultyCodeAllocator._norm(prefix)
        # Highest numeric suffix among codes of the form <PREFIX><digits>.
        row = await db.execute(
            text(
                """
                SELECT COALESCE(MAX(
                    CAST(SUBSTRING(faculty_code FROM (char_length(:prefix) + 1)) AS INTEGER)
                ), 0) AS max_seq
                FROM sis_faculty_profiles
                WHERE faculty_code ~ ('^' || :prefix || '[0-9]+$')
                """
            ),
            {"prefix": p},
        )
        max_seq = int(row.scalar_one() or 0)
        if max_seq <= 0:
            return
        await db.execute(
            text(
                """
                INSERT INTO faculty_code_counters (prefix, next_value)
                VALUES (:prefix, :next_value)
                ON CONFLICT (prefix)
                DO UPDATE SET next_value = GREATEST(faculty_code_counters.next_value, :next_value),
                              updated_at = now()
                """
            ),
            {"prefix": p, "next_value": max_seq + 1},
        )
