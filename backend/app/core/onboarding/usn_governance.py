"""USN code governance — ERP Onboarding Phase 1 / Step 5.

Issued USNs encode immutable academic identity:

    {SchoolCode}{YY}{ProgramCode}{Sequence}      e.g.  SCA26MCA001

Once a USN has been issued, the *school code* and *program code* baked into it
can never change (names may).  These reusable helpers answer the single question
each update guard needs: "is this code already cemented into an issued USN?"

Matching is structural (anchored regex) rather than a naive substring, so a
school code ``SC`` does not falsely match ``SCA26...`` and a program code ``CA``
does not falsely match the ``SCA`` school segment:

  * school code  → leading alpha segment immediately before the 2-digit year:
        ^<CODE><2 digits>
  * program code → segment between the 2-digit year and the trailing sequence:
        ^<alpha><2 digits><CODE><digits>$

The scan targets ``sis_student_profiles.usn`` (the canonical issued-USN store).
Comparison is case-insensitive.
"""
from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Codes are validated elsewhere as short alphanumerics; strip anything else
# defensively so a stray character can never alter the regex semantics.
_SAFE = re.compile(r"[^A-Za-z0-9]")


def _clean(code: str) -> str:
    return _SAFE.sub("", code or "")


class SchoolCodeUsageService:
    """Whether a school code is cemented into any issued USN."""

    @staticmethod
    async def is_school_code_used(school_code: str, db: AsyncSession) -> bool:
        code = _clean(school_code)
        if not code:
            return False
        pattern = f"^{code}[0-9]{{2}}"
        row = await db.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM sis_student_profiles "
                "WHERE usn IS NOT NULL AND usn ~* :pat)"
            ),
            {"pat": pattern},
        )
        return bool(row.scalar_one())


class ProgramCodeUsageService:
    """Whether a program code is cemented into any issued USN."""

    @staticmethod
    async def is_program_code_used(program_code: str, db: AsyncSession) -> bool:
        code = _clean(program_code)
        if not code:
            return False
        pattern = f"^[A-Za-z]+[0-9]{{2}}{code}[0-9]+$"
        row = await db.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM sis_student_profiles "
                "WHERE usn IS NOT NULL AND usn ~* :pat)"
            ),
            {"pat": pattern},
        )
        return bool(row.scalar_one())
