"""tenant: M06 — add instructions field to lab_assignments

Revision ID: 0026ten
Revises: 0025ten
Create Date: 2026-05-30

Changes
-------
  lab_assignments.instructions (TEXT, nullable) — student submission instructions,
  separate from the problem statement (description).

Backward compat: all existing rows get NULL; publish guard only requires description.
"""

import sqlalchemy as sa
from alembic import op

revision      = "0026ten"
down_revision = "0025ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "lab_assignments",
        sa.Column("instructions", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lab_assignments", "instructions")
