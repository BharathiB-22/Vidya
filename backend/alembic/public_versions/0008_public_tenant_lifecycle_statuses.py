"""public: add INACTIVE and ARCHIVED tenant lifecycle statuses

Revision ID: 0008pub
Revises: 0007pub
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa

revision = "0008pub"
down_revision = "0007pub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # tenant.status is stored as VARCHAR (native_enum=False on the SQLAlchemy model);
    # there is no PostgreSQL ENUM type or CHECK constraint to alter.
    # This migration documents the addition of INACTIVE and ARCHIVED as valid
    # lifecycle status values for the tenant management lifecycle controls.
    pass


def downgrade() -> None:
    pass
