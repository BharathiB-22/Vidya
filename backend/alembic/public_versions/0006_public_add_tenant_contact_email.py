"""public: add contact_email to tenants

Revision ID: 0006pub
Revises: 0005pub
Create Date: 2026-05-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0006pub"
down_revision = "0005pub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("contact_email", sa.String(), nullable=True),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("tenants", "contact_email", schema="public")
