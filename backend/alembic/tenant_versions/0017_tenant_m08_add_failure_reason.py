"""tenant: m08 exam_papers add failure_reason column

Revision ID: 0017ten
Revises: 0016ten
Create Date: 2026-05-25

Notes:
  Adds a nullable TEXT column to exam_papers to store human-readable
  generation-failure details when status == 'FAILED'.
  No existing rows are affected (column is nullable, no default required).
  The 'FAILED' status value itself requires no schema change because
  exam_papers.status is stored as VARCHAR (native_enum=False).
"""

import sqlalchemy as sa
from alembic import op

revision      = "0017ten"
down_revision = "0016ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "exam_papers",
        sa.Column("failure_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("exam_papers", "failure_reason")
