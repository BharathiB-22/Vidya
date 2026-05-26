"""public: add branding fields to tenants

Revision ID: 0007pub
Revises: 0006pub
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa

revision = "0007pub"
down_revision = "0006pub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("logo_url", sa.String(), nullable=True),
        schema="public",
    )
    op.add_column(
        "tenants",
        sa.Column("primary_color", sa.String(7), nullable=True),
        schema="public",
    )
    op.add_column(
        "tenants",
        sa.Column("secondary_color", sa.String(7), nullable=True),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("tenants", "secondary_color", schema="public")
    op.drop_column("tenants", "primary_color", schema="public")
    op.drop_column("tenants", "logo_url", schema="public")
