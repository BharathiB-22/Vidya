"""USN allocation — concurrency-safe sequence reservation.

Phase 1 / Step 1 of the Intelligent ERP Onboarding programme.

USN format:  ``{SchoolCode}{YY}{ProgramCode}{Seq}``   e.g.  ``SCA26MCA001``

``allocate_block`` reserves a contiguous range of sequence numbers for a
``(school_code, admission_year, program_code)`` triple using an atomic
``INSERT ... ON CONFLICT DO UPDATE ... RETURNING``.  The ON CONFLICT row lock
serialises concurrent callers, so issued ranges never overlap and contain no
gaps.  The sequence resets per triple — ``SCA/2026/MCA`` starts at 001
independently of ``SCA/2026/BCA`` and of ``SCA/2027/MCA``.

USNs mint on commit only: call ``allocate_block`` inside the same transaction
that writes the student rows, so an aborted commit releases the reserved numbers
(the counter increment rolls back with it).

The allocator never writes to ``acad_*`` master data and never edits an existing
USN — it only hands out new numbers.  USN immutability is enforced separately at
the profile/import write layer (Phase 1, Step 5).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class UsnAllocatorError(ValueError):
    """Raised for invalid allocation arguments (bad count or missing codes)."""


# Unified atomic reservation.  In BOTH the insert and the conflict path the
# returned ``next_seq`` is the value *after* incrementing by ``count``, so the
# start of the reserved block is always ``returned - count``:
#   • first insert  → next_seq = count + 1, start = (count + 1) - count = 1
#   • on conflict   → next_seq = prev + count, start = (prev + count) - count = prev
_ALLOC_SQL = text(
    """
    INSERT INTO usn_sequence_counters
        (school_code, admission_year, program_code, next_seq)
    VALUES (:school_code, :admission_year, :program_code, :count + 1)
    ON CONFLICT (school_code, admission_year, program_code)
    DO UPDATE SET next_seq   = usn_sequence_counters.next_seq + :count,
                  updated_at = now()
    RETURNING next_seq
    """
)


class UsnAllocator:

    # ------------------------------------------------------------------ #
    # Normalisation                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _norm(school_code: str, program_code: str) -> tuple[str, str]:
        sc = (school_code or "").strip().upper()
        pc = (program_code or "").strip().upper()
        if not sc:
            raise UsnAllocatorError("school_code is required")
        if not pc:
            raise UsnAllocatorError("program_code is required")
        return sc, pc

    # ------------------------------------------------------------------ #
    # Atomic block reservation                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def allocate_block(
        db: AsyncSession,
        *,
        school_code: str,
        admission_year: int,
        program_code: str,
        count: int,
    ) -> int:
        """Reserve ``count`` contiguous sequence numbers; return the first one.

        The reserved block is ``[start, start + count - 1]``.  Atomic and safe
        under concurrent callers sharing the same triple.
        """
        if count < 1:
            raise UsnAllocatorError("count must be >= 1")
        sc, pc = UsnAllocator._norm(school_code, program_code)

        result = await db.execute(
            _ALLOC_SQL,
            {
                "school_code": sc,
                "admission_year": int(admission_year),
                "program_code": pc,
                "count": int(count),
            },
        )
        new_next = int(result.scalar_one())
        return new_next - count

    # ------------------------------------------------------------------ #
    # Formatting                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def format_usn(
        school_code: str,
        admission_year: int,
        program_code: str,
        seq: int,
        *,
        width: int = 3,
    ) -> str:
        """Render a USN string, e.g. ``SCA26MCA001``.

        ``admission_year`` is the full year (2026); the 2-digit suffix is used.
        """
        sc, pc = UsnAllocator._norm(school_code, program_code)
        if seq < 1:
            raise UsnAllocatorError("seq must be >= 1")
        yy = int(admission_year) % 100
        return f"{sc}{yy:02d}{pc}{seq:0{width}d}"

    # ------------------------------------------------------------------ #
    # Convenience: reserve + format in one call                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def allocate_usns(
        db: AsyncSession,
        *,
        school_code: str,
        admission_year: int,
        program_code: str,
        count: int,
        width: int = 3,
    ) -> list[str]:
        """Reserve ``count`` USNs and return the formatted strings, in order."""
        start = await UsnAllocator.allocate_block(
            db,
            school_code=school_code,
            admission_year=admission_year,
            program_code=program_code,
            count=count,
        )
        return [
            UsnAllocator.format_usn(
                school_code, admission_year, program_code, start + i, width=width
            )
            for i in range(count)
        ]
