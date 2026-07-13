"""tenant: the Board's hours per unit — Phase A V2.4

Revision ID: 0088ten
Revises: 0087ten
Create Date: 2026-07-13

The unit COUNT was the Board's decision (0087ten). The HOURS are too, and for the
same reason: they come out of the timetable and the credit structure, and the model
has no way of knowing that Unit III is the heavy one this year.

So the Board states them before generation — [10, 8, 12, 10] — and the generator
writes each unit TO its hours rather than inventing its own and leaving the Board to
redistribute them afterwards. The units are then saved with exactly these figures,
and the course total is their sum.

Empty ([]) means the Board did not say, which is what every existing syllabus means:
the model paces the units against the contact hours on its own, exactly as before.
Nothing is backfilled, because there is nothing to backfill — a syllabus generated
before this had no hour plan, and inventing one for it retrospectively would be
claiming a decision the Board never made.

The list lives on the syllabus rather than in the job payload for the same reason
unit_count does: a regeneration months from now has to produce the same shape as the
document it replaces, and only the row remembers what was asked for.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision      = "0088ten"
down_revision = "0087ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "syllabi",
        sa.Column(
            "unit_hours",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("syllabi", "unit_hours")
