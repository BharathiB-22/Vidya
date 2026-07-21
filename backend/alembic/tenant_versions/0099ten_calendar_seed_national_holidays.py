"""tenant: national holidays get an author-less origin, and are seeded (P1.19)

Revision ID: 0099ten
Revises: 0098ten
Create Date: 2026-07-16

Two changes, both in service of the Academic Calendar actually having something
on it the day a tenant is created.

1. academic_events.created_by_user_id becomes nullable.

   Every event so far was declared by a person, so the column was NOT NULL. A
   national holiday has no author — nobody at the institution decided that
   Independence Day is the 15th of August. NULL now means exactly that: seeded
   reference data, not somebody's decision. Existing rows all have a creator and
   are untouched.

2. India's three FIXED-DATE national holidays are seeded for 2026-2030:

       26 January   Republic Day
       15 August    Independence Day
       2  October   Gandhi Jayanti

   These three and only these three. They are the national holidays whose dates
   are fixed in the Gregorian calendar, so they can be computed years ahead
   without guessing. Diwali, Holi, Eid, Good Friday and the rest move every year
   against this calendar — hardcoding them would put a wrong date in front of a
   student, which is worse than showing nothing. Those stay what they already
   are: declared by the Admin/Dean who knows this year's date, through the
   existing /calendar/events endpoints. University holidays are likewise the
   institution's own to declare.

   The seed is idempotent: it skips any date that already carries a
   GOVERNMENT_HOLIDAY, so re-running it — or running it on a tenant whose admin
   already entered them by hand — cannot produce duplicates.

Downgrade removes only the rows this seeded (author-less GOVERNMENT_HOLIDAYs on
those exact dates), never an event a person declared.
"""
import sqlalchemy as sa
from alembic import op

revision      = "0099ten"
down_revision = "0098ten"
branch_labels = None
depends_on    = None

# (month, day, title) — fixed-date national holidays only.
_NATIONAL_HOLIDAYS = (
    (1,  26, "Republic Day"),
    (8,  15, "Independence Day"),
    (10, 2,  "Gandhi Jayanti"),
)

_YEARS = range(2026, 2031)


def upgrade() -> None:
    op.alter_column(
        "academic_events",
        "created_by_user_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    conn = op.get_bind()
    for year in _YEARS:
        for month, day, title in _NATIONAL_HOLIDAYS:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO academic_events (
                        id, title, description, event_type,
                        start_at, end_at, is_all_day,
                        visibility, created_by_user_id, created_at
                    )
                    SELECT gen_random_uuid(), :title, :description,
                           'GOVERNMENT_HOLIDAY',
                           make_timestamptz(:year, :month, :day, 0, 0, 0), NULL, true,
                           'ALL', NULL, now()
                    WHERE NOT EXISTS (
                        SELECT 1 FROM academic_events e
                        WHERE e.event_type = 'GOVERNMENT_HOLIDAY'
                          AND e.start_at::date
                              = make_date(:year, :month, :day)
                    )
                    """
                ),
                {
                    "title": title,
                    "description": "National holiday.",
                    "year": year,
                    "month": month,
                    "day": day,
                },
            )


def downgrade() -> None:
    conn = op.get_bind()
    for year in _YEARS:
        for month, day, _title in _NATIONAL_HOLIDAYS:
            conn.execute(
                sa.text(
                    """
                    DELETE FROM academic_events
                    WHERE event_type = 'GOVERNMENT_HOLIDAY'
                      AND created_by_user_id IS NULL
                      AND start_at::date = make_date(:year, :month, :day)
                    """
                ),
                {"year": year, "month": month, "day": day},
            )

    # Anything author-less that survived would break the NOT NULL, so this only
    # tightens the column when nothing seeded remains.
    conn.execute(
        sa.text("DELETE FROM academic_events WHERE created_by_user_id IS NULL")
    )
    op.alter_column(
        "academic_events",
        "created_by_user_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
