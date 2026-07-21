"""tenant: coursework AI provider tracking (multi-provider fallback)

Revision ID: 0102ten
Revises: 0101ten
Create Date: 2026-07-21

Additive columns on assignment_evaluations to record which AI provider produced a
result and the fallback path taken (Gemini -> Groq -> DeepSeek):

    provider_used   the provider that returned the stored result, e.g. "groq".
    fallback_chain  the ordered chain attempted, e.g. "gemini→groq".

No existing column or table is changed; both are nullable and backfill to NULL for
existing rows. `model_used` is the pre-existing `ai_model` column; `retry_count`
already exists.
"""
import sqlalchemy as sa
from alembic import op

revision      = "0102ten"
down_revision = "0101ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column("assignment_evaluations", sa.Column("provider_used", sa.String(), nullable=True))
    op.add_column("assignment_evaluations", sa.Column("fallback_chain", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("assignment_evaluations", "fallback_chain")
    op.drop_column("assignment_evaluations", "provider_used")
