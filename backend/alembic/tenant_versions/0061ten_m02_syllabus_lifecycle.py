"""tenant: M02 syllabus academic lifecycle — REJECTED status + dean_comment

Adds:
  - dean_comment column on syllabi (stores Dean's rejection / revision feedback)
  - No enum column change required (status is stored as VARCHAR, not a native PG enum)

Revision ID: 0061ten
Revises: 0060ten
Create Date: 2026-06-29
"""

import sqlalchemy as sa
from alembic import op

revision      = "0061ten"
down_revision = "0060ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "syllabi",
        sa.Column("dean_comment", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("syllabi", "dean_comment")
