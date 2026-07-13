"""tenant: an elective basket is not a course — remove the placeholders

Revision ID: 0089ten
Revises: 0088ten
Create Date: 2026-07-13

An elective basket is a curriculum SLOT: "Elective 1, semester 3, 3 credits". The
student takes exactly one subject from it. The subjects inside it — Artificial
Intelligence, Data Mining, Cloud Computing — are real courses, each with a code, a
syllabus, a lecturer and an examination. The slot has none of those things.

Two slots were nevertheless living in `courses`:

    MCA305  "Elective 1"   THEORY  semester 3   (inside basket "Elective 1")
    MCA308  "Elective 2"   THEORY  semester 3   (inside basket "Elective 2")

They came from the curriculum generator, whose prompt told the model that "an elective
paper is ONE curriculum course" while also asking for that paper's alternatives — so
it emitted both, and the ingest saved both. The prompt and the ingest are fixed (see
m01/electives.py, which is now the single definition of this mistake and is enforced
on every path that creates or renames a course). This migration removes what the old
code already wrote.

The damage was not cosmetic. A placeholder carries a course code, takes a course type,
is handed its own official syllabus to generate, and stands in the curriculum's
approve gate — blocking the whole curriculum until a Board approves a syllabus for a
subject that nobody teaches and nobody sits.

WHAT THIS DELETES, and what it deliberately will not
----------------------------------------------------
A row is removed only when EVERY one of these holds:

  * it is an elective, and it sits inside a basket
  * its title is a slot label ("Elective 2", "Professional Elective III") or is
    exactly the name of the basket it sits in
  * its programme is NOT approved or published
  * it has NO syllabus
  * nothing academic points at it: no registrations, no timetable slot, no faculty
    assignment, no attendance session, no marks component, no exam schedule, no
    external marks, no result

Everything else is left exactly where it is, and reported instead:

  * An approved or published curriculum is frozen history. A placeholder inside one is
    a blemish on a record that a university has already issued, and silently rewriting
    an issued record is worse than the blemish. It stays; the Board can fork the
    curriculum if it matters.
  * A placeholder that somehow carries a syllabus or a student's marks is not a
    placeholder any more — something real is attached to it, and no migration should
    decide what happens to that. It stays, and is named in the log.

On the data as it stands this deletes exactly the two rows above, in one tenant. Every
other tenant is a no-op.

Irreversible by design: the down-revision cannot recreate a row that should never have
existed, and would not want to.
"""

from alembic import op

revision      = "0089ten"
down_revision = "0088ten"
branch_labels = None
depends_on    = None


# The slot label, as SQL. Mirrors m01/electives.py — the Python guard stops new ones
# being written, this removes the ones the old code already wrote, and the two must
# agree about what a slot looks like.
_SLOT_TITLE = (
    r"^\s*(professional|open|programme|program|departmental|department|core|discipline)?"
    r"\s*elective\s*(paper|basket|slot|group)?\s*[-–:.#]?\s*([0-9]+|[ivx]+)?\s*$"
)

# Everything that could be pointing at a course. If ANY of them is, the row is not an
# empty placeholder and this migration does not touch it.
_DEPENDENTS = (
    ("syllabi",                 "course_id"),
    ("elective_registrations",  "course_id"),
    ("timetable_slots",         "course_id"),
    ("subject_assignments",     "course_id"),
    ("sis_attendance_sessions", "course_id"),
    ("sis_marks_components",    "course_id"),
    ("sis_exam_schedules",      "course_id"),
    ("sis_external_marks",      "course_id"),
    ("sis_subject_results",     "course_id"),
)


def _candidate_predicate() -> str:
    """A course that is really a slot: elective, in a basket, titled like one."""
    return f"""
        c.is_elective = true
        AND c.elective_basket_id IS NOT NULL
        AND (
            lower(btrim(c.title)) = lower(btrim(b.name))
            OR c.title ~* '{_SLOT_TITLE}'
        )
    """


def _unused_predicate() -> str:
    """Nothing academic points at it — checked against every table that could.

    `to_regclass` because a tenant that is behind on migrations may not have all of
    these tables yet: an absent table cannot be holding a row that blocks the delete,
    and a migration that crashed on it would strand exactly the universities most in
    need of the repair.
    """
    clauses = [
        f"""
        (to_regclass(current_schema() || '.{table}') IS NULL
         OR NOT EXISTS (
            SELECT 1 FROM {table} d WHERE d.{column} = c.id
         ))
        """
        for table, column in _DEPENDENTS
    ]
    return " AND ".join(clauses)


def upgrade() -> None:
    # Say what is about to happen, and what is being left alone, BEFORE doing it —
    # a migration that deletes rows silently is one nobody can audit afterwards.
    op.execute(
        f"""
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            FOR r IN
                SELECT c.code, c.title, b.name AS basket, p.status, p.title AS program
                  FROM courses c
                  JOIN elective_baskets b ON b.id = c.elective_basket_id
                  JOIN programs p ON p.id = c.program_id
                 WHERE {_candidate_predicate()}
            LOOP
                RAISE NOTICE
                    '0089ten: elective-slot placeholder % (%) in basket % — programme % [%]',
                    r.title, r.code, r.basket, r.program, r.status;
            END LOOP;
        END $$;
        """
    )

    op.execute(
        f"""
        DELETE FROM courses c
         USING elective_baskets b, programs p
         WHERE b.id = c.elective_basket_id
           AND p.id = c.program_id
           AND p.status NOT IN ('APPROVED', 'PUBLISHED')
           AND {_candidate_predicate()}
           AND {_unused_predicate()}
        """
    )


def downgrade() -> None:
    """Nothing to undo.

    These rows were a defect: a curriculum slot masquerading as a taught subject. A
    downgrade that recreated them would be recreating the bug, and there is no
    information in the schema from which to rebuild them faithfully anyway.
    """
