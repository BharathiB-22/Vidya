"""tenant: the Board's teaching hours and weeks — Phase A V2.5

Revision ID: 0090ten
Revises: 0089ten
Create Date: 2026-07-14

How long a subject is taught for was, until now, arithmetic: (L + T + P) x 15 weeks,
a figure the system computed and nobody could argue with. For a 4-0-0 course that is
60 hours, and 60 hours is what the generator was told to write to — whatever the Board
knew about the semester it was actually planning for.

A semester is not always 15 weeks. It is shortened by an election, a late start, a
festival calendar; a subject may be taught intensively over 10, or stretched across an
18-week autonomous term. The L-T-P is the weekly load, and multiplying it by a constant
is a SUGGESTION about the term, not a fact about it.

So the two figures the suggestion is made of are now the Board's to state:

    teaching_hours   the total taught hours of the course — what the units add up to,
                     and what the AI paces the syllabus against
    teaching_weeks   how many weeks the term runs, which is what makes the hours a
                     suggestion worth showing in the first place

NULL means the Board did not say, which is what every existing syllabus means: the
figure is derived from the course's L-T-P exactly as before (m02/formatting.py:
derive_contact_hours). Nothing is backfilled — writing 60 into a row whose Board never
chose 60 would be recording a decision as if a human had made it, which is the one
thing this column exists to stop.

On the syllabus rather than in the job payload, for the same reason unit_count (0087ten)
and unit_hours (0088ten) are: a regeneration months from now has to write to the same
shape as the document it replaces, and only the row remembers what was asked for.
"""

import sqlalchemy as sa
from alembic import op

revision      = "0090ten"
down_revision = "0089ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column("syllabi", sa.Column("teaching_hours", sa.Integer(), nullable=True))
    op.add_column("syllabi", sa.Column("teaching_weeks", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("syllabi", "teaching_weeks")
    op.drop_column("syllabi", "teaching_hours")
