"""Deterministic curriculum course codes.

Course codes used to come from wherever: the AI generator invented them, and a
Dean adding an elective choice typed one by hand. Both routes let two courses in
one program collide on `UniqueConstraint("program_id", "code")`, and neither
produced the sequence an institution actually expects.

A code is `{PREFIX}{semester}{NN}`:

    MCA, semester 3   ->  MCA301, MCA302, MCA303, ...
    BCA, semester 2   ->  BCA201, BCA202, ...
    BSCCS, semester 5 ->  BSCCS501, BSCCS502, ...

WHERE THE PREFIX COMES FROM — and where it must never come from
---------------------------------------------------------------
The prefix is `acad_programs.code`: the institution's OWN identifier for the
programme, typed by the institution, unique per tenant, and reachable from any
curriculum through `programs.acad_program_id`.

It is deliberately NOT derived from anything else, because everything else is a
guess:

  - `programs.degree_type` is a LEVEL, not a code. A real MCA curriculum in this
    system carries degree_type "PG", which would yield PG101 — wrong, and wrong
    in a way that looks plausible enough to ship.
  - the title ("Master of Computer Applications") is prose. Turning prose into an
    identifier is exactly the guessing this module exists to stop.
  - the AI's own codes are worse still: a model asked for an MCA curriculum
    returns CS501, because it is naming the subject discipline — it cannot know
    what the institution calls its programmes, and nothing in the prompt could
    honestly tell it.

So a curriculum with no `acad_program_id` has no code, and this module says so
(ProgramCodePrefixError) rather than inventing one. AI generation refuses to
start without the link; see ProgramService.generate_structure.

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


class ProgramCodePrefixError(Exception):
    """This curriculum is not attached to an institutional programme, so there is
    no code to prefix its courses with.

    Callers translate this into their own vocabulary — a 422 at the API, a failed
    job in the worker — but nobody may paper over it with a fallback prefix. See
    the module docstring: a wrong prefix is worse than a missing one, because it
    persists into every course code, every syllabus header and every transcript
    without ever looking wrong enough to question.
    """


def normalise_prefix(code: str) -> str:
    """'B.Sc CS' -> 'BSCCS'. Upper-cased, stripped of anything that is not a
    letter or digit.

    Applied to `acad_programs.code` so an institution that types its own code with
    a dot or a space still gets a usable identifier. It does NOT invent a prefix
    from a degree type or a title — see the module docstring.
    """
    return re.sub(r"[^A-Za-z0-9]", "", code or "").upper()


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


def assign_course_codes(
    courses: list[dict],
    prefix: str,
    taken: set[str],
) -> dict[str, str]:
    """Give every course in `courses` a backend-owned code, in place.

    Returns the map from whatever code the course arrived with (the AI's `CS501`)
    to the code it was assigned (`MCA101`). That map is not a diagnostic — it is
    load-bearing: the AI expresses prerequisites as `prerequisite_codes: ["CS501"]`,
    and once the codes are rewritten those references resolve to nothing unless
    they are translated through it. A silently empty prerequisite graph is the
    failure this returns a value to prevent.

    `taken` is seeded with the codes already in the program (human-authored
    courses survive AI regeneration) and grows as codes are handed out, because
    the uniqueness constraint is program-wide.

    Courses are numbered per semester in list order, so the sequence follows the
    curriculum as the AI laid it out rather than an accident of dict ordering.

    A duplicate incoming code — the AI can and does emit the same code twice —
    still yields two distinct assigned codes, but only the FIRST claims the entry
    in the map: a prerequisite naming an ambiguous code cannot be resolved to one
    course, and quietly picking the last one would be a guess.
    """
    if not prefix:
        raise ProgramCodePrefixError("Cannot assign course codes without a prefix.")

    assigned: dict[str, str] = {}
    for course in sorted(courses, key=lambda c: c.get("semester") or 0):
        old = (course.get("code") or "").strip()
        new = next_free_code(prefix, course["semester"], taken)
        taken.add(new)
        course["code"] = new
        if old and old not in assigned:
            assigned[old] = new
    return assigned


async def resolve_program_prefix(program_id: UUID, *, db: AsyncSession) -> str:
    """The institution's code for the programme this curriculum belongs to.

    Raises ProgramCodePrefixError when the curriculum is not linked to an
    `acad_programs` row. That is a real, reachable state — `acad_program_id` is
    nullable and curricula predate the link — and it is the one case where
    refusing to act is the correct behaviour.
    """
    row = (await db.execute(
        text(
            "SELECT ap.code FROM programs p "
            "JOIN acad_programs ap ON ap.id = p.acad_program_id "
            "WHERE p.id = :pid"
        ),
        {"pid": str(program_id)},
    )).scalar_one_or_none()

    prefix = normalise_prefix(row or "")
    if not prefix:
        raise ProgramCodePrefixError(
            "This curriculum is not linked to an academic programme, so its courses "
            "have no institutional code to be numbered under. Set the programme "
            "(e.g. MCA) on the curriculum, then generate."
        )
    return prefix


async def generate_course_code(program_id: UUID, semester: int, db: AsyncSession) -> str:
    """Next free `{PREFIX}{semester}{NN}` for this program.

    Reads every existing code in the program because the uniqueness constraint
    is program-wide; a code that looks like it belongs to another semester still
    blocks reuse.
    """
    prefix = await resolve_program_prefix(program_id, db=db)
    rows = (await db.execute(
        text("SELECT code FROM courses WHERE program_id = :pid"),
        {"pid": str(program_id)},
    )).scalars().all()
    return next_free_code(prefix, semester, set(rows))
