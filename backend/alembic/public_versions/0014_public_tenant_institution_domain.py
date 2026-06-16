"""public: add institution_domain to tenants

Phase 1.2 / Task C — Institution Email Foundation.

Stores the email domain used to mint institution email addresses for a
tenant's students ({usn}@{domain}) and faculty ({employee_id}@{domain}).
Generation only — login is unaffected by this change.

Revision ID: 0014pub
Revises: 0013pub
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa

revision = "0014pub"
down_revision = "0013pub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("institution_domain", sa.String(), nullable=True),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("tenants", "institution_domain", schema="public")
