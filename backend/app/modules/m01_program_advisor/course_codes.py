"""Deterministic curriculum course codes.

Course codes used to come from wherever: the AI generator invented them, and a
Dean adding an elective choice typed one by hand. Both routes let two courses in
one program collide on `UniqueConstraint("program_id", "code")`, and neither
produced the sequence an institution actually expects.

A code is `{PREFIX}{semester}{NN}`:

    MCA, semester 3   ->  MCA301, MCA302, MCA303, ...
    BCA, semester 2   ->  BCA201, BCA202, ...
    B.Tech, semester 5 -> BTECH501, BTECH502, ...

The prefix comes from the program's `degree_type`, normalised the same way
`compliance.classify_degree_level` normalises it (dots, spaces and hyphens
stripped) so "B.Tech", "b tech" and "B-Tech" all yield BTECH.

Nothing here assumes a particular semester. Semester 10 simply yields MCA1001 —
the semester number is concatenated, not packed into a fixed width.
"""
from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# A code is only ever generated into a gap or onto the end of the sequence, so a
# program that already holds MCA301..MCA305 yields MCA306 next.
_MAX_SEQ = 999


def normalise_prefix(degree_type: str) -> str:
    """'B.Tech' -> 'BTECH'. Mirrors compliance.py's degree_type normalisation,
    upper-cased and stripped of anything that is not a letter or digit."""
    return re.sub(r"[^A-Za-z0-9]", "", degree_type or "").upper()


def format_course_code(prefix: str, semester: int, seq: int) -> str:
    """`seq` is zero-padded to two digits but never truncated, so a program with
    more than 99 courses in one semester keeps producing valid codes."""
    return f"{prefix}{semester}{seq:02d}"


def next_free_code(prefix: str, semester: int, taken: set[str]) -> str:
    """The first code in the sequence that `taken` does not already contain.

    Pure so it can be tested without a database. `taken` should be every code in
    the program, not just this semester's — codes are unique per program.
    """
    if not prefix:
        raise ValueError("Cannot generate a course code without a degree prefix.")
    for seq in range(1, _MAX_SEQ + 1):
        code = format_course_code(prefix, semester, seq)
        if code not in taken:
            return code
    raise ValueError(
        f"Exhausted course codes for {prefix} semester {semester} "
        f"after {_MAX_SEQ} attempts."
    )


async def generate_course_code(program_id: UUID, degree_type: str, semester: int, db: AsyncSession) -> str:
    """Next free `{PREFIX}{semester}{NN}` for this program.

    Reads every existing code in the program because the uniqueness constraint
    is program-wide; a code that looks like it belongs to another semester still
    blocks reuse.
    """
    rows = (await db.execute(
        text("SELECT code FROM courses WHERE program_id = :pid"),
        {"pid": str(program_id)},
    )).scalars().all()
    return next_free_code(normalise_prefix(degree_type), semester, set(rows))
