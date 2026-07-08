"""tenant: add optional remarks to timetable_slots (Phase 4.2)

Revision ID: 0076ten
Revises: 0075ten
Create Date: 2026-07-08

Additive-only: a nullable free-text `remarks` column on timetable_slots so the
timetable builder can record a note per slot (e.g. "Tutorial", "Guest
lecture"). Pre-existing slots keep working unchanged.
"""

import sqlalchemy as sa
from alembic import op

revision      = "0076ten"
down_revision = "0075ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column("timetable_slots", sa.Column("remarks", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("timetable_slots", "remarks")
