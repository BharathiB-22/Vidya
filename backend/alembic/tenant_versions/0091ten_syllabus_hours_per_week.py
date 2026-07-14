"""tenant: hours per week, not weeks — P1.10

Revision ID: 0091ten
Revises: 0090ten
Create Date: 2026-07-14

0090ten gave the Board two figures: the total taught hours, and the WEEKS the term
runs. The hours were right. The weeks were the wrong second figure, and the syllabus
a university actually prints says so:

    Total Teaching Hours: 52          No. of Hours / Week: 04

Hours per week is what the header carries, what a timetable is built from, and what a
Board says out loud. Weeks are the arithmetic BETWEEN those two — 52 over 4 a week is
thirteen weeks — and a system that stores a derivable number invites the day it
disagrees with the two it was derived from.

So `teaching_weeks` becomes `hours_per_week`, carrying its meaning across rather than
losing it: a syllabus that said "52 hours over 13 weeks" now says "52 hours, 4 a week",
which is the same fact in the words the document uses. Where the arithmetic does not
divide (49 hours over 13 weeks is 3.77 a week) it rounds, because an hours-per-week of
4 is what such a course is actually timetabled at, and the total hours — the figure the
AI and the units are held to — is untouched either way.

Nullable, as before: NULL means the Board has not said, and nothing derives it. Weeks,
where the generator still wants them for pacing, are now computed from these two.
"""

import sqlalchemy as sa
from alembic import op

revision      = "0091ten"
down_revision = "0090ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column("syllabi", sa.Column("hours_per_week", sa.Integer(), nullable=True))

    # Carry the meaning across. GREATEST(...,1) because a syllabus taught for fewer
    # hours than it has weeks would otherwise land on 0 hours a week, which is not a
    # course; ROUND because a timetable is built in whole hours.
    op.execute(
        """
        UPDATE syllabi
           SET hours_per_week = GREATEST(ROUND(teaching_hours::numeric / teaching_weeks), 1)
         WHERE teaching_hours IS NOT NULL
           AND teaching_weeks IS NOT NULL
           AND teaching_weeks > 0
        """
    )
    op.drop_column("syllabi", "teaching_weeks")


def downgrade() -> None:
    op.add_column("syllabi", sa.Column("teaching_weeks", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE syllabi
           SET teaching_weeks = GREATEST(ROUND(teaching_hours::numeric / hours_per_week), 1)
         WHERE teaching_hours IS NOT NULL
           AND hours_per_week IS NOT NULL
           AND hours_per_week > 0
        """
    )
    op.drop_column("syllabi", "hours_per_week")
