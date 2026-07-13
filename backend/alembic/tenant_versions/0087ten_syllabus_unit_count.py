"""tenant: the Board decides how many units — Phase A V2.4

Revision ID: 0087ten
Revises: 0086ten
Create Date: 2026-07-13

Five units was hardcoded. It is not a universal format: plenty of AICTE, VTU and
autonomous regulations run to four, and a Board that wants four had no way to say
so — it generated five and then deleted one, which left the hours redistributed by
hand and the AI's own pacing wrong across the units that survived.

So the unit count is now a decision the Board makes BEFORE generation, and it is
stored on the syllabus rather than passed transiently to the job: the worker reads
it, the AI is asked for exactly that many units, and the validator rejects a
response that returns a different number. A regeneration months later must produce
the same shape as the original, and the only way to guarantee that is for the row
itself to remember what was asked for.

Four or five. Not three (no regulation is taught in three) and not six (nobody
prints Unit VI). The bound is enforced in the API schema; the column is a plain
integer with a default of five, which is what every existing syllabus was
generated with.

Non-theory documents ignore it entirely — an internship has no units and a lab
manual has experiments. The column exists on every row because it is cheaper than
a nullable one that means "not applicable here", and the generator never reads it
for a type that has no units.
"""

import sqlalchemy as sa
from alembic import op

revision      = "0087ten"
down_revision = "0086ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "syllabi",
        sa.Column(
            "unit_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
        ),
    )


def downgrade() -> None:
    op.drop_column("syllabi", "unit_count")
