"""tenant: persist paper template (source of truth) (P1.16)

Revision ID: 0094ten
Revises: 0093ten
Create Date: 2026-07-16

Two additive, nullable columns so a paper preserves its selected template from
creation through to PDF export:

    exam_papers.template_type        "UNIT" | "SECTION" | "FULL_QUESTION" | "HYBRID"
    exam_papers.template_definition  the exact template configuration (JSONB):
                                     {type, blocks:[...]} for section/full/hybrid,
                                     {type, units:[...]} for unit.

The existing `blueprint` column remains the internal generation model (compiled
from the template). Legacy papers have NULL template_* and fall back to blueprint
/ flat rendering, so this is a pure additive change with no backfill and nothing
downstream needs to change (AI generation, seal, release, marks are untouched).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0094ten"
down_revision = "0093ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column("exam_papers", sa.Column("template_type", sa.String(), nullable=True))
    op.add_column(
        "exam_papers",
        sa.Column("template_definition", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("exam_papers", "template_definition")
    op.drop_column("exam_papers", "template_type")
