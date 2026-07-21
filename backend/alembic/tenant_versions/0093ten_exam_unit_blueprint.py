"""tenant: per-unit paper blueprint (P1.16)

Revision ID: 0093ten
Revises: 0092ten
Create Date: 2026-07-16

One additive, nullable column for the per-unit paper blueprint (m08):

    exam_papers.blueprint    [{unit_number: int, rows: [{count: int, marks: float}]}]
                             Faculty define, per unit, how many questions of each
                             mark value the paper should contain. Drives AI
                             generation exactly and is the target plan for manual
                             papers. NULL for existing papers (they keep using
                             question_format / section_config), so this is a pure
                             additive change with no backfill.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0093ten"
down_revision = "0092ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "exam_papers",
        sa.Column("blueprint", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("exam_papers", "blueprint")
