"""tenant: an elective slot owns its own publish + registration lifecycle

Revision ID: 0079ten
Revises: 0078ten
Create Date: 2026-07-10

Until now an elective slot's editability was inherited from its program: courses
(and therefore elective choices) may only be added while the program is DRAFT or
PENDING_APPROVAL. That makes the required workflow impossible — a Dean cannot add
a choice to Elective 1 of a PUBLISHED program, which is exactly when they need to.

The slot now carries its own lifecycle, independent of the program:

    DRAFT      choices may be added, edited, removed
    PUBLISHED  choice list is frozen; students can see the slot
    OPEN       students may choose / switch their one option
    CLOSED     choices frozen; the roster is final

The split is deliberate. The slot's *definition* (name, credits, semester) stays
governed by the program's status, because slot credits feed compliance and the
program credit total and must freeze when the curriculum does. The slot's
*contents* (which subjects it offers) are a catalogue concern and are governed
here instead. Different programs may open their electives at different times.

Backfill keeps every existing tenant working exactly as it does today:
  - a slot that already has registrations must stay registerable  -> OPEN
  - a slot on a published program is visible but not yet open      -> PUBLISHED
  - anything else is still being drafted                           -> DRAFT
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision      = "0079ten"
down_revision = "0078ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "elective_baskets",
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
    )
    op.add_column("elective_baskets", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("elective_baskets", sa.Column("published_by_user_id", UUID(as_uuid=True), nullable=True))
    op.add_column("elective_baskets", sa.Column("registration_opened_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("elective_baskets", sa.Column("registration_closed_at", sa.DateTime(timezone=True), nullable=True))

    # A slot students have already registered against must remain registerable,
    # otherwise this upgrade would silently strand them mid-semester.
    op.execute(
        """
        UPDATE elective_baskets b
        SET status = 'OPEN',
            published_at = COALESCE(b.published_at, now()),
            registration_opened_at = COALESCE(b.registration_opened_at, now())
        WHERE EXISTS (
            SELECT 1 FROM elective_registrations er WHERE er.basket_id = b.id
        )
        """
    )
    op.execute(
        """
        UPDATE elective_baskets b
        SET status = 'PUBLISHED',
            published_at = COALESCE(b.published_at, now())
        FROM programs p
        WHERE p.id = b.program_id
          AND p.status = 'PUBLISHED'
          AND b.status = 'DRAFT'
        """
    )

    op.create_index("ix_elective_baskets_status", "elective_baskets", ["status"])


def downgrade() -> None:
    op.drop_index("ix_elective_baskets_status", table_name="elective_baskets")
    op.drop_column("elective_baskets", "registration_closed_at")
    op.drop_column("elective_baskets", "registration_opened_at")
    op.drop_column("elective_baskets", "published_by_user_id")
    op.drop_column("elective_baskets", "published_at")
    op.drop_column("elective_baskets", "status")
