"""Drop kit_quizlets table.

Phase 1 regression fix: Course Kit MCQ generation/CRUD/display/compliance/
export was removed entirely — the ORM model, repository, and all API
surfaces were deleted. This migration drops the now-fully-unreferenced
table so no orphaned schema object remains.

Revision ID: 0064ten
Revises: 0063ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0064ten"
down_revision = "0063ten"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_kit_quizlets_kit", table_name="kit_quizlets")
    op.drop_table("kit_quizlets")


def downgrade() -> None:
    op.create_table(
        "kit_quizlets",
        sa.Column("id",                 postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kit_id",             postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_number",    sa.Integer(),                  nullable=False),
        sa.Column("question_text",      sa.Text(),                     nullable=False),
        sa.Column("question_type",      sa.String(),                   nullable=False, server_default="MCQ"),
        sa.Column("options",            postgresql.JSONB(),            nullable=False, server_default="[]"),
        sa.Column("answer_key",         postgresql.JSONB(),            nullable=False, server_default="{}"),
        sa.Column("answer_explanation", sa.Text(),                     nullable=True),
        sa.Column("bloom_level",        sa.String(),                   nullable=True),
        sa.Column("co_reference",       sa.String(),                   nullable=True),
        sa.Column("created_at",         sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",         sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["kit_id"], ["course_kits.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("kit_id", "question_number"),
    )
    op.create_index("ix_kit_quizlets_kit", "kit_quizlets", ["kit_id"])
