"""tenant: add users.avatar_url (Phase 4.2)

Revision ID: 0074ten
Revises: 0073ten
Create Date: 2026-07-07

Single source of truth for a profile picture across all tenant roles
(Student/Faculty/Dean/Admin) — uploaded via the existing storage module
(entity_type="avatar") and referenced here as a resolved, viewable URL.
"""

import sqlalchemy as sa
from alembic import op

revision      = "0074ten"
down_revision = "0073ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_url")
