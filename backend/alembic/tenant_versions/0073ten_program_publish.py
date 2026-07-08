"""tenant: add Program publish lock (Phase 4.2)

Revision ID: 0073ten
Revises: 0072ten
Create Date: 2026-07-07

Adds programs.published_by_user_id / published_at so a Program can move
Draft -> Approved -> Published, with edit/delete blocked only once
Published (Draft and Approved both remain editable/deletable). status
remains a plain VARCHAR (native_enum=False), so no type migration is
needed for the new PUBLISHED value.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0073ten"
down_revision = "0072ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column("programs", sa.Column("published_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("programs", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("programs", "published_at")
    op.drop_column("programs", "published_by_user_id")
