"""public: add DELETED tenant lifecycle status

Revision ID: 0009pub
Revises: 0008pub
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa

revision = "0009pub"
down_revision = "0008pub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # tenant.status is stored as VARCHAR (native_enum=False on the SQLAlchemy model);
    # there is no PostgreSQL ENUM type or CHECK constraint to alter.
    # This migration documents the addition of DELETED as a valid lifecycle status
    # for soft-deleting test/demo tenants from the Super Admin portal.
    pass


def downgrade() -> None:
    pass
