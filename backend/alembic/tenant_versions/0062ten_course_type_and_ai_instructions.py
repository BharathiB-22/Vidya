"""Add course_type to courses and ai_instructions to programs.

Phase 4: MCA credit flexibility — course_type drives compliance credit limits.
Phase 5: AI instructions field — persists curriculum generation guidance.

Revision ID: 0062ten
Revises: 0061ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0062ten"
down_revision = "0061ten"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column(
            "course_type",
            sa.String(length=20),
            nullable=True,
            server_default=None,
        ),
    )
    op.add_column(
        "programs",
        sa.Column("ai_instructions", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("courses", "course_type")
    op.drop_column("programs", "ai_instructions")
