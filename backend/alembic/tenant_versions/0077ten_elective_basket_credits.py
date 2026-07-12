"""tenant: an elective basket is a curriculum SLOT that owns its credits

Revision ID: 0077ten
Revises: 0076ten
Create Date: 2026-07-09

0075ten made a basket a group of real option courses. It did not give the
basket a credit weight of its own, so "how many credits does Elective 1
contribute?" was answered by peeking at the member courses (max of members in
the UI, first member in the generator). That derivation breaks in the two
cases a real ERP hits constantly:

  - an empty basket contributes 0 credits, so a Dean who creates the slot
    before filling it sees the curriculum total drop;
  - options are allowed to disagree (AI301 = 3cr, DM301 = 4cr) and whichever
    one happened to sort first silently decided the curriculum's number.

The slot is a curriculum fact, independent of which options currently hang off
it: Elective 1 is worth 3 credits whether it holds three options or zero.

Backfill preserves today's effective total exactly: each existing basket takes
the max credits among its members (the same value the UI already displayed),
falling back to 3 for empty baskets. No user-facing migration step.
"""

import sqlalchemy as sa
from alembic import op

revision      = "0077ten"
down_revision = "0076ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "elective_baskets",
        sa.Column("credits", sa.Integer(), nullable=True, server_default="3"),
    )
    op.execute(
        """
        UPDATE elective_baskets b
        SET credits = COALESCE(
            (SELECT MAX(c.credits) FROM courses c WHERE c.elective_basket_id = b.id),
            3
        )
        """
    )
    op.alter_column("elective_baskets", "credits", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    op.drop_column("elective_baskets", "credits")
